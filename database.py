import os
import time
import threading
import uuid
import re
from datetime import datetime, timedelta
import socket
from google import genai
from google.cloud import firestore
from google.cloud import storage
from google.cloud import secretmanager

# --- CONFIGURATION ---
PROJECT_ID = "gen-lang-client-0351290071"
SECRET_ID = "GEMINI_API_KEY"
BUCKET_NAME = "ldn-chat-audio-uploads-035129"

def is_emulator_ready(host_port):
    if not host_port: return False
    try:
        host, port = host_port.split(":")
        # Optimization: Only 1 retry with short timeout to avoid long hangs
        with socket.create_connection((host, int(port)), timeout=0.5):
            return True
    except:
        return False

# Global Clients (Initialized lazily in init_db)
db = None
storage_client = None
sm = None
gemini_client = None
BOT_ENABLED = False
DEJA_VU_ENABLED = False
GEMINI_KEY = None
_db_initialized = False

def get_secret(secret_id, version_id="latest"):
    global sm
    if sm is None:
        sm = secretmanager.SecretManagerServiceClient()
    name = f"projects/{PROJECT_ID}/secrets/{secret_id}/versions/{version_id}"
    response = sm.access_secret_version(request={"name": name})
    return response.payload.data.decode("UTF-8")

CACHE_DIR = "assets/cache"
UPLOAD_DIR = "uploads"

# --- STATE ---
analysis_buffer = []
last_observation = "The channel is silent."
observer_lens = "concise, slightly dry, insightful, and technical"
ANALYSIS_TRIGGER = 10
TRAFFIC_WINDOW = 60.0
buffer_start_time = 0.0
buffer_lock = threading.Lock()

local_sessions = set()
typing_status = {}
DECAY_TIMEOUT = 3.0

# --- DATA MODEL ---
class Message:
    def __init__(self, user_name, text, message_type, timestamp, uid, audio_data=None, db_id=None):
        self.user_name = user_name
        self.text = text
        self.message_type = message_type
        self.timestamp = timestamp
        self.uid = uid
        self.audio_data = audio_data
        self.db_id = db_id

    def to_dict(self):
        return {
            "user_name": self.user_name, "text": self.text, "message_type": self.message_type,
            "timestamp": self.timestamp, "uid": self.uid, "audio_data": self.audio_data, "db_id": self.db_id
        }

def register_session(pubsub):
    local_sessions.add(pubsub)

def unregister_session(pubsub):
    if pubsub in local_sessions:
        local_sessions.remove(pubsub)

def broadcast(message_data):
    if not local_sessions:
        return
    def _do_broadcast():
        # Copy the sessions to avoid "set changed size during iteration" errors
        sessions = list(local_sessions)
        for session in sessions:
            try:
                session.send_all(message_data)
            except Exception as e:
                # If a session fails, unregister it locally to prevent future failures
                if session in local_sessions:
                    local_sessions.remove(session)
    threading.Thread(target=_do_broadcast, daemon=True).start()

# --- FIRESTORE LISTENERS ---
def on_messages_snapshot(col_snapshot, changes, read_time):
    for change in changes:
        type_str = str(change.type).split('.')[-1]
        if type_str == 'ADDED':
            doc = change.document.to_dict()
            raw_ts = doc.get("timestamp")
            if hasattr(raw_ts, "strftime"):
                final_ts = raw_ts.strftime("%H:%M")
            else:
                final_ts = str(raw_ts)
            broadcast({
                "user_name": doc.get("user_name"), 
                "text": doc.get("text"), 
                "message_type": doc.get("message_type"),
                "timestamp": final_ts, 
                "uid": doc.get("uid"), 
                "audio_data": doc.get("audio_data"), 
                "db_id": change.document.id
            })
        elif type_str == 'REMOVED':
            doc = change.document.to_dict()
            uid = doc.get("uid")
            broadcast({"message_type": "delete_message", "uid": uid})

def on_typing_snapshot(col_snapshot, changes, read_time):
    for change in changes:
        type_str = str(change.type).split('.')[-1]
        if type_str == 'ADDED':
            doc = change.document.to_dict()
            broadcast({"message_type": "typing_signal", "user_name": doc.get("user_name")})

def init_db():
    global db, storage_client, sm, gemini_client, BOT_ENABLED, GEMINI_KEY, _db_initialized
    if _db_initialized:
        return
    _db_initialized = True
    
    print("Backend: Initializing Database Clients...")
    
    # Firestore Client
    f_host = os.getenv("FIRESTORE_EMULATOR_HOST")
    if f_host and is_emulator_ready(f_host):
        print(f"Backend: Using Firestore Emulator at {f_host}")
        os.environ["FIRESTORE_EMULATOR_HOST"] = f_host
    elif f_host:
        print(f"WARNING: Firestore Emulator not reachable. Falling back.")
        if "FIRESTORE_EMULATOR_HOST" in os.environ: del os.environ["FIRESTORE_EMULATOR_HOST"]
    db = firestore.Client(project=PROJECT_ID)

    # Storage Client
    s_host = os.getenv("STORAGE_EMULATOR_HOST")
    if s_host and is_emulator_ready(s_host):
        print(f"Backend: Using Storage Emulator at {s_host}")
        os.environ["STORAGE_EMULATOR_HOST"] = s_host
    elif s_host:
        if "STORAGE_EMULATOR_HOST" in os.environ: del os.environ["STORAGE_EMULATOR_HOST"]
    storage_client = storage.Client(project=PROJECT_ID)

    # Gemini Client
    try:
        GEMINI_KEY = get_secret(SECRET_ID)
    except Exception as e:
        print(f"Backend: Secret Error, trying env: {e}")
        GEMINI_KEY = os.getenv("GEMINI_API_KEY")

    if GEMINI_KEY:
        try:
            gemini_client = genai.Client(api_key=GEMINI_KEY)
            BOT_ENABLED = True
            print("Backend: Gemini Bot Enabled.")
        except Exception as e:
            print(f"Backend: Gemini Config Error: {e}")

    os.makedirs(CACHE_DIR, exist_ok=True)
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    
    # Start Real-time Listeners in background thread to avoid blocking main thread
    def start_listeners():
        now = datetime.now()
        print("Backend: Starting Firestore Listeners...")
        try:
            db.collection("messages").where(filter=firestore.FieldFilter("timestamp", ">", now)).on_snapshot(on_messages_snapshot)
            db.collection("typing_signals").on_snapshot(on_typing_snapshot)
            print("Backend: Firestore Listeners requested.")
        except Exception as e:
            print(f"Backend: Listener Error (might be offline): {e}")

    threading.Thread(target=start_listeners, daemon=True).start()
    threading.Thread(target=_signal_cleanup_loop, daemon=True).start()

def get_uptime():
    # Cloud Run doesn't have /proc/uptime in the same way, but it's fine to keep as a dummy or return "On Cloud"
    return "Google Cloud Run"

# --- SYNC LOOPS (Firestore replaces the polling loop!) ---
def _signal_cleanup_loop():
    while True:
        time.sleep(30)
        try:
            limit_time = datetime.now() - timedelta(seconds=10)
            # Find old signals
            old_signals = db.collection("typing_signals").where(filter=firestore.FieldFilter("timestamp", "<", limit_time)).stream()
            
            batch = db.batch()
            count = 0
            for s in old_signals:
                batch.delete(s.reference)
                count += 1
                # Firestore batch limit is 500
                if count >= 500:
                    batch.commit()
                    batch = db.batch()
                    count = 0
            
            if count > 0:
                batch.commit()
        except Exception as e:
            print(f"Signal Cleanup Error: {e}")

def send_typing_signal(user_name):
    # Optimistic broadcast for local feel
    broadcast({"message_type": "typing_signal", "user_name": user_name})
    threading.Thread(target=_write_typing_signal, args=(user_name,), daemon=True).start()

def _write_typing_signal(user_name):
    try:
        db.collection("typing_signals").add({
            "user_name": user_name,
            "timestamp": datetime.now()
        })
    except Exception as e:
        print(f"Typing Signal Insert Error: {e}")

# --- GENAI & CORE LOGIC ---
def _run_gemini_background(transcript):
    global last_observation, observer_lens
    try:
        prompt = f"""
        You are an Observer Node in a digital chat room.

        CURRENT LENS: {observer_lens}

        Previous Observation State: "{last_observation}"

        Task: Analyze the new transcript below. Connect it to the Previous Observation. 
        How has the mood shifted? What is the new connection?

        Style: Adhere strictly to the CURRENT LENS.
        Length: Maximum 2 sentences.

        New Transcript:
        {transcript}
        """
        response = gemini_client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt
        )
        if response and response.text:
            text = response.text.strip()
            last_observation = text
            insert_message("OBSERVER_NODE", text, "analysis_message")
    except Exception as e:
        print(f"Backend: Analysis Failed: {e}")

def insert_message(user_name, text, message_type, is_temp=False, audio_payload=None):
    global analysis_buffer, buffer_start_time, observer_lens

    # --- 1. INTERCEPT: SLASH COMMANDS ---
    if text and text.startswith("/lens "):
        new_lens = text.replace("/lens ", "").strip()
        if len(new_lens) < 150:
            observer_lens = new_lens
            broadcast({
                "user_name": "SYSTEM",
                "text": f"Observer Lens shifted to: {new_lens}",
                "message_type": "login_message",
                "timestamp": datetime.now().strftime("%H:%M"),
                "uid": str(uuid.uuid4())
            })
            return

    if text and text.startswith("/capsule "):
        try:
            parts = text.split(" ", 2)
            if len(parts) >= 3:
                duration_str = parts[1]
                content = parts[2]
                delay_seconds = 0
                if "s" in duration_str: delay_seconds = int(duration_str.replace("s", ""))
                elif "m" in duration_str: delay_seconds = int(duration_str.replace("m", "")) * 60
                elif "h" in duration_str: delay_seconds = int(duration_str.replace("h", "")) * 3600

                if delay_seconds > 0:
                    broadcast({
                        "user_name": "SYSTEM",
                        "text": f"Capsule sealed. Opening in {duration_str}...",
                        "message_type": "login_message",
                        "timestamp": datetime.now().strftime("%H:%M"),
                        "uid": str(uuid.uuid4())
                    })
                    threading.Timer(delay_seconds, insert_message,
                                    args=[user_name, content, message_type, is_temp, audio_payload]).start()
                    return
        except Exception as e:
            print(f"Capsule Error: {e}")

    # --- 2. CORE: DB INSERTION (Firestore) ---
    now_obj = datetime.now()
    ui_ts = now_obj.strftime("%H:%M")
    new_uid = str(uuid.uuid4())

    # DÉJÀ VU CHECK (Firestore Version) - MOVED TO ASYNC THREAD TO AVOID BLOCKING
    if message_type == "chat_message" and text and len(text) > 15:
        threading.Thread(target=_check_deja_vu_async, args=(text, now_obj, ui_ts), daemon=True).start()

    # Write to Firestore
    try:
        # We skip the optimistic broadcast for standard chat messages to prevent "double updates"
        # and WebSocket thrashing on mobile. The Firestore listener will handle the UI update.
        if message_type != "chat_message":
            broadcast({
                "user_name": user_name,
                "text": text,
                "message_type": message_type,
                "timestamp": ui_ts,
                "uid": new_uid,
                "audio_data": audio_payload,
                "db_id": None
            })
        
        doc_ref = db.collection("messages").document()
        base_data = {
            "user_name": user_name,
            "text": text,
            "message_type": message_type,
            "timestamp": now_obj,
            "uid": new_uid,
            "audio_data": audio_payload
        }
        
        if is_temp:
            print(f"DEBUG: Setting expiry for temporary message {new_uid}")
            base_data["expires_at"] = now_obj + timedelta(seconds=60)
            
        doc_ref.set(base_data)
    except Exception as e:
        print(f"CRITICAL: Firestore Insert Failed: {e}")

    # --- 3. ANALYTICS: OBSERVER NODE ---
    if BOT_ENABLED and message_type == "chat_message":
        with buffer_lock:
            current_time = time.time()
            if analysis_buffer:
                if current_time - buffer_start_time > TRAFFIC_WINDOW:
                    analysis_buffer = []

            if not analysis_buffer: buffer_start_time = current_time

            analysis_buffer.append(f"{user_name}: {text}")

            if len(analysis_buffer) >= ANALYSIS_TRIGGER:
                elapsed = current_time - buffer_start_time
                transcript_snapshot = "\n".join(analysis_buffer)
                analysis_buffer = []

                if elapsed <= TRAFFIC_WINDOW:
                    threading.Thread(target=_run_gemini_background, args=(transcript_snapshot,), daemon=True).start()

    if is_temp:
        print(f"DEBUG: Starting delete_later thread for {new_uid}")
        threading.Thread(target=delete_later, args=(new_uid, 60), daemon=True).start()

def _check_deja_vu_async(text, now_obj, ui_ts):
    try:
        # Query Firestore for duplicates
        # Note: If this requires a composite index, it might still fail, 
        # but at least it won't block the main chat.
        docs = db.collection("messages").where(filter=firestore.FieldFilter("text", "==", text)).order_by("timestamp", direction=firestore.Query.ASCENDING).limit(1).stream(timeout=5.0)
        for doc in docs:
            ddata = doc.to_dict()
            past_user = ddata.get("user_name")
            past_time = ddata.get("timestamp")
            if (now_obj - past_time.replace(tzinfo=None)).total_seconds() > 300:
                deja_vu_ref = f"⟳ Connection identified: Originally stated by {past_user} on {past_time.strftime('%Y-%m-%d')}"
                time.sleep(0.5)
                broadcast({
                    "user_name": "ARCHIVE",
                    "text": deja_vu_ref,
                    "message_type": "login_message",
                    "timestamp": ui_ts,
                    "uid": str(uuid.uuid4())
                })
            break
    except Exception as e:
        print(f"Deja Vu Error: {e}")

def delete_later(uid, delay):
    print(f"DEBUG: delete_later called for {uid} with delay {delay}")
    time.sleep(delay)
    # Firestore delete
    try:
        print(f"DEBUG: Attempting Firestore deletion for {uid}")
        docs = db.collection("messages").where(filter=firestore.FieldFilter("uid", "==", uid)).stream()
        found = False
        for doc in docs:
            doc.reference.delete()
            print(f"DEBUG: Deleted document {doc.id} for UID {uid}")
            found = True
        if not found:
            print(f"DEBUG: No document found for UID {uid} during deletion")
    except Exception as e:
        print(f"DEBUG: Error in delete_later for {uid}: {e}")
        pass
    broadcast({"message_type": "delete_message", "uid": uid})

def get_recent_messages(limit=50):
    messages = []
    try:
        print("DATABASE: get_recent_messages - Streaming from Firestore...")
        # Get latest 50 messages ordered by timestamp
        docs = db.collection("messages").order_by("timestamp", direction=firestore.Query.DESCENDING).limit(limit).stream(timeout=5.0)
        
        now = datetime.now()
        for doc in docs:
            r = doc.to_dict()
            
            # Check for expiration
            expires_at = r.get("expires_at")
            if expires_at and hasattr(expires_at, "replace"):
                if expires_at.replace(tzinfo=None) < now:
                    print(f"DEBUG: Skipping expired message {r.get('uid')}")
                    continue

            raw_ts = r.get("timestamp")
            
            # Firestore timestamp to UI string
            if hasattr(raw_ts, "strftime"):
                final_ts = raw_ts.strftime("%H:%M")
            else:
                final_ts = str(raw_ts)

            messages.append(Message(r["user_name"], r["text"], r["message_type"], final_ts, r["uid"], r.get("audio_data"), doc.id))
        
        print(f"DATABASE: get_recent_messages - Successfully retrieved {len(messages)} messages.")
        # NO REVERSE: We want index 0 to be the NEWEST message
        # because ListView(reverse=True) expects newest messages at index 0.
    except Exception as e:
        print(f"DATABASE: Get Messages Error: {e}")
    return messages

def clear_global_database():
    try:
        # Batch delete for efficiency
        batch = db.batch()
        docs = db.collection("messages").stream()
        for doc in docs:
            batch.delete(doc.reference)
        batch.commit()
        broadcast({"message_type": "clear_signal"})
        return True
    except:
        return False

def fetch_message_with_retry(db_id):
    try:
        doc = db.collection("messages").document(db_id).get()
        if doc.exists:
            r = doc.to_dict()
            raw_ts = r.get("timestamp")
            if hasattr(raw_ts, "strftime"):
                final_ts = raw_ts.strftime("%H:%M")
            else:
                final_ts = str(raw_ts)
            return Message(r["user_name"], r["text"], r["message_type"], final_ts, r["uid"], r.get("audio_data"), doc.id)
    except:
        pass
    return None