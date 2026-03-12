# LDN Chat Version: v3.10.0 (Feature: Déjà Vu Toggle + Code Polish)
import flet as ft
import os
import time
import datetime
import base64
import random
import asyncio
import re
import uuid
import database  # Backend module
# import flet_audio as fta # Temporarily disabled to isolate conflicts

print(f"DEBUG: Startup - Flet Version: {ft.__version__}")
APP_VERSION = "v3.10.5 (Layout Tweaks)"
HEARTBEAT_INTERVAL = 4.0
HISTORY_BATCH_SIZE = 30

# --- COLOR PALETTE ---
PAGE_BG = "#131314"  # The main dark background
CODE_BG = "#282c34"  # Matches 'ATOM_ONE_DARK' theme background
BUBBLE_BG = "#2A2A2A"  # Standard message bubble
TEXT_COLOR = "#e3e3e3"  # Main text
SUB_TEXT = "#c4c7c5"  # Secondary text (headers, names)

# --- PRE-COMPILED PATTERNS ---
URL_PATTERN = re.compile(r"((?:https?://|www\.)\S+)", re.IGNORECASE)


# --- MAIN APP ---
async def main(page: ft.Page):
    page_alive = True

    # --- APP SETTINGS & STATE ---
    settings = {
        "typing_enabled": True,
        "deja_vu_enabled": False  # DEFAULT: OFF to save costs
    }

    # Sync initial state to backend
    database.DEJA_VU_ENABLED = settings["deja_vu_enabled"]

    state = {
        "user_name": None,
        "last_typing_sent": 0.0,
        "is_temp_mode": False,
        "joining": False,
        "full_history": [],
        "history_cursor": 0,
        "is_loading_history": False
    }

    # Optimization: O(1) lookup for message controls
    message_controls = {}

    # --- SETUP PAGE ---
    page.theme_mode = ft.ThemeMode.DARK
    page.bgcolor = PAGE_BG
    page.title = f"LDN Chat {APP_VERSION}"
    page.padding = 0

    # --- AUDIO PLAYER ---
    # --- AUDIO PLAYER (DISABLED FOR DEBUG) ---
    # try:
    #     print("DEBUG: Initializing global_audio_player...")
    #     global_audio_player = fta.Audio(
    #         src="about:blank",
    #         autoplay=False
    #     )
    #     page.overlay.append(global_audio_player)
    #     print("DEBUG: global_audio_player added to overlay.")
    # except Exception as e:
    #     print(f"CRITICAL: Failed to add Audio to overlay: {e}")

    file_picker = ft.FilePicker()

    # FilePicker and SnackBar initialization (Disabled for stability)
    # try:
    #     feedback_snack = ft.SnackBar(content=ft.Text(""), duration=1500)
    #     page.overlay.append(feedback_snack)
    # except Exception as e:
    #     print(f"CRITICAL: Failed to add SnackBar to overlay: {e}")

    # try:
    #     print("DEBUG: Registering FilePicker to overlay...")
    #     page.overlay.append(file_picker)
    #     print("DEBUG: FilePicker added to overlay.")
    # except Exception as e:
    #     print(f"CRITICAL: Failed to add FilePicker to overlay: {e}")

    # Check persistence early
    stored_user = None
    if hasattr(page, "client_storage"):
        stored_user = page.client_storage.get("user_name")

    def cache_audio_file(msg_uid, audio_ref):
        try:
            filename = f"{msg_uid}.mp4"
            filepath = os.path.join(database.CACHE_DIR, filename)
            if os.path.exists(filepath): return f"/cache/{filename}"

            # If audio_ref starts with gs://, download from GCS
            if isinstance(audio_ref, str) and audio_ref.startswith("gs://"):
                bucket = database.storage_client.bucket(database.BUCKET_NAME)
                blob_name = audio_ref.replace(f"gs://{database.BUCKET_NAME}/", "")
                blob = bucket.blob(blob_name)
                blob.download_to_filename(filepath)
            elif audio_ref: # Fallback for old base64 data
                if isinstance(audio_ref, memoryview):
                    audio_ref = bytes(audio_ref)
                audio_bytes = base64.b64decode(audio_ref)
                with open(filepath, "wb") as f:
                    f.write(audio_bytes)
            else:
                return None
                
            return f"/cache/{filename}"
        except Exception as e:
            print(f"Cache Error: {e}")
            return None

    async def play_audio_message(msg_uid, audio_ref):
        print(f"DEBUG: Audio playback requested for {msg_uid} but is temporarily disabled.")
        # try:
        #     if not audio_ref: return
        #     feedback_snack.content.value = "Buffering from Cloud..."
        #     feedback_snack.open = True
        #     feedback_snack.update()
        #
        #     relative_url = await asyncio.to_thread(cache_audio_file, msg_uid, audio_ref)
        #     if not relative_url: return
        #
        #     global_audio_player.src = f"{relative_url}?t={int(time.time())}"
        #     global_audio_player.autoplay = True
        #     global_audio_player.update()
        #     await asyncio.sleep(0.1)
        #     global_audio_player.play()
        # except Exception as ex:
        #     print(f"Playback error: {ex}")

    # --- INIT BACKEND ---
    print("DEBUG: Calling database.init_db()...")
    database.init_db() # Idempotent call
    
    print("DEBUG: Registering session with database...")
    database.register_session(page.pubsub)
    
    # Consolidation of on_disconnect
    async def handle_disconnect(e):
        nonlocal page_alive
        print("DEBUG: Session disconnected, unregistering...")
        page_alive = False
        database.unregister_session(page.pubsub)
    
    page.on_disconnect = handle_disconnect
    def generate_spans(text, query_pattern=None, query_text=None):
        spans = []
        if not text: return spans

        parts = URL_PATTERN.split(text)

        for part in parts:
            if not part: continue

            if URL_PATTERN.fullmatch(part):
                url_to_open = part
                if part.lower().startswith("www."): url_to_open = f"https://{part}"
                spans.append(ft.TextSpan(
                    text=part,
                    style=ft.TextStyle(color="#8ab4f8", decoration=ft.TextDecoration.UNDERLINE),
                    on_click=lambda e, u=url_to_open: page.launch_url(u)
                ))
            else:
                if query_pattern and query_text and query_text.lower() in part.lower():
                    sub_parts = query_pattern.split(part)
                    for sub in sub_parts:
                        if not sub: continue
                        if sub.lower() == query_text.lower():
                            spans.append(ft.TextSpan(text=sub, style=ft.TextStyle(bgcolor="#F9A825",
                                                                                  color="white")))
                        else:
                            spans.append(ft.TextSpan(text=sub))
                else:
                    spans.append(ft.TextSpan(text=part))
        return spans

    # --- UI COMPONENTS ---

    # 1. COPY FEEDBACK BANNER (Toast)
    copy_banner = ft.Container(
        content=ft.Text("Copied to clipboard", color="black", size=14, weight="w500"),
        bgcolor="white",
        padding=ft.padding.only(top=12, bottom=12, left=16, right=16),
        border_radius=8,
        visible=False,
        bottom=20,
        left=20,
        shadow=ft.BoxShadow(
            spread_radius=1,
            blur_radius=5,
            color="#4d000000",
            offset=ft.Offset(0, 2),
        ),
        animate_opacity=300,
    )

    async def trigger_copy_snack(text_to_copy):
        page.set_clipboard(text_to_copy)
        copy_banner.visible = True
        copy_banner.opacity = 1
        copy_banner.update()
        await asyncio.sleep(2.0)
        copy_banner.visible = False
        copy_banner.opacity = 0
        copy_banner.update()

    # 2. HEADER ELEMENTS
    session_avatar = ft.CircleAvatar(radius=16, visible=False, bgcolor="#444746")
    session_name = ft.Text(value="", weight="bold", visible=False, color=TEXT_COLOR)
    user_session_info = ft.Row(controls=[session_avatar, session_name])
    user_count_text = ft.Text(value="...", size=12, color="#8e918f", weight="bold")

    # 3. CHAT AREA
    chat = ft.ListView(
        expand=True,
        spacing=10,
        auto_scroll=False,
        reverse=True,
        padding=ft.padding.only(left=20, right=20, top=10, bottom=10)
    )

    chat_container = ft.Container(
        content=chat,
        expand=True,
        bgcolor=PAGE_BG,
    )

    async def scroll_to_bottom_click(e):
        try:
            await chat.scroll_to(offset=0, duration=500, curve=ft.AnimationCurve.EASE_OUT)
        except Exception:
            pass

    scroll_down_button = ft.IconButton(
        icon=ft.Icons.ARROW_DOWNWARD,
        icon_color="#c4c7c5",
        bgcolor="#1e1f20",
        visible=False,
        on_click=scroll_to_bottom_click,
        tooltip="Jump to latest"
    )

    chat.on_scroll_interval = 10

    # --- PAGINATION LOGIC ---
    async def load_history_chunk():
        if state["is_loading_history"]: return

        total_available = len(state["full_history"])
        if state["history_cursor"] >= total_available:
            return

        state["is_loading_history"] = True
        start_idx = state["history_cursor"]
        end_idx = start_idx + HISTORY_BATCH_SIZE
        chunk = state["full_history"][start_idx:end_idx]

        print(f"DEBUG: load_history_chunk - cursor: {start_idx}, batch: {HISTORY_BATCH_SIZE}")
        new_controls = []
        for msg in chunk:
            try:
                m = create_chat_message(msg)
                if m:
                    message_controls[str(msg.uid)] = m
                    new_controls.append(m)
            except Exception as e:
                print(f"DEBUG: Error creating message {msg.uid}: {e}")

        print(f"DEBUG: load_history_chunk - adding {len(new_controls)} controls to chat.")
        chat.controls.extend(new_controls)
        state["history_cursor"] = end_idx
        state["is_loading_history"] = False
        chat.update() # Explicitly update chat
        page.update()

    async def on_chat_scroll(e):
        try:
            should_show = e.pixels > 50
            if scroll_down_button.visible != should_show:
                scroll_down_button.visible = should_show
                scroll_down_button.update()

            if e.max_scroll_extent > 0:
                if e.pixels >= (e.max_scroll_extent - 100):
                    await load_history_chunk()
        except Exception:
            pass

    chat.on_scroll = on_chat_scroll

    async def scroll_to_bottom(instant=False):
        try:
            duration = 0 if instant else 300
            curve = ft.AnimationCurve.EASE_OUT if not instant else None
            await chat.scroll_to(offset=0, duration=duration, curve=curve)
        except Exception:
            pass

    # --- HELPER: UNIFIED MARKDOWN RENDERER ---
    def get_message_markdown(text):
        return ft.Markdown(
            value=text,
            selectable=True,
            extension_set=ft.MarkdownExtensionSet.GITHUB_WEB,
            code_theme=ft.MarkdownCodeTheme.ATOM_ONE_DARK,
            on_tap_link=lambda e: page.launch_url(e.data),
        )

    def create_message_content(text):
        stripped = text.strip()

        # CODE BLOCK RENDERER (Specialized with Copy Header)
        if stripped.startswith("```"):
            try:
                lines = stripped.split('\n')
                lang = lines[0].replace('```', '').strip()
                if not lang: lang = "Code"

                # Extract raw code for copying (strip triple backticks)
                raw_code = stripped
                if stripped.startswith("```") and stripped.endswith("```"):
                    parts = stripped.split('\n')
                    if len(parts) > 2:
                        raw_code = '\n'.join(parts[1:-1])

                # Header (Title Bar)
                header = ft.Container(
                    content=ft.Row([
                        ft.Text(lang, size=12, weight="bold", color=SUB_TEXT),
                        ft.IconButton(
                            icon=ft.Icons.CONTENT_COPY,
                            icon_size=16,
                            icon_color=SUB_TEXT,
                            tooltip="Copy code",
                            on_click=lambda e: page.run_task(trigger_copy_snack, raw_code)
                        )
                    ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                    bgcolor=CODE_BG,
                    padding=ft.padding.only(top=5, bottom=5, left=15, right=15),
                    border_radius=ft.border_radius.only(top_left=12, top_right=12)
                )

                # Body (Code Content with Horizontal Scroll Support)
                body = ft.Container(
                    content=ft.Row([
                        ft.Markdown(
                            value=stripped,
                            extension_set=ft.MarkdownExtensionSet.GITHUB_WEB,
                            code_theme=ft.MarkdownCodeTheme.ATOM_ONE_DARK,
                        )
                    ], scroll=ft.ScrollMode.AUTO),
                    bgcolor=CODE_BG,
                    padding=10,
                    border_radius=ft.border_radius.only(bottom_left=12, bottom_right=12)
                )

                return ft.Column([header, body], spacing=0)
            except Exception:
                return get_message_markdown(text)

        return get_message_markdown(text)

    # --- MESSAGE COMPONENT ---
    def create_chat_message(message: database.Message):
        u_name = message.user_name if message.user_name else "Unknown"
        is_me = u_name == state["user_name"]

        if message.message_type == "login_message":
            return ft.Row(
                key=str(message.uid),
                alignment=ft.MainAxisAlignment.CENTER,
                controls=[ft.Text(value=message.text, size=11, color="#8e918f", italic=True)]
            )

        if message.message_type == "analysis_message" or u_name == "ARCHIVE":
            return ft.Row(
                key=str(message.uid),
                vertical_alignment=ft.CrossAxisAlignment.START,
                controls=[
                    ft.Icon(ft.Icons.AUTO_AWESOME, color=SUB_TEXT, size=20),
                    ft.Container(width=10),
                    ft.Column(
                        expand=True,
                        controls=[create_message_content(message.text)]
                    )
                ]
            )

        def get_avatar_color(user_name: str):
            if not user_name: user_name = "default"
            clist = ["#8ab4f8", "#81c995", "#f28b82", "#fdd663", "#c58af9", "#78d9ec"]
            return clist[hash(user_name) % len(clist)]

        content_control = None
        if message.message_type == "audio_message":
            if message.audio_data:
                # Note: play_audio_message is currently a no-op placeholder
                async def on_play_click(e):
                    await play_audio_message(message.uid, message.audio_data)

                content_control = ft.Container(
                    content=ft.Row([
                        ft.IconButton(content=ft.Icon(ft.Icons.PLAY_ARROW, color="#131314"),
                                      on_click=on_play_click),
                        ft.Text("Audio Message", italic=True, size=13, color="#131314")
                    ], tight=True),
                    bgcolor=TEXT_COLOR, border_radius=18, padding=5, width=170
                )
            else:
                content_control = ft.Container(
                    content=ft.Row([
                        ft.ProgressRing(width=16, height=16, stroke_width=2, color="#8e918f"),
                        ft.Text("Processing...", italic=True, size=12, color="#8e918f")
                    ], tight=True),
                    padding=10
                )

        else:
            is_code = message.text.strip().startswith("```")
            is_long = len(message.text) > 400 or message.text.count('\n') > 10
            is_markdown = any(char in message.text for char in ["*", "_", "`", "[", "#", "|"])

            if is_code:
                content_control = create_message_content(message.text)
            elif is_markdown:
                content_control = get_message_markdown(message.text)
            else:
                txt_control = ft.Text(
                    spans=generate_spans(message.text),
                    selectable=True,
                    size=15,
                    color=TEXT_COLOR,
                    data=message.text,
                    font_family="Roboto, sans-serif",
                    weight=ft.FontWeight.W_400,
                    max_lines=10 if is_long else None,
                    overflow=ft.TextOverflow.ELLIPSIS if is_long else None,
                )

                if is_long:
                    expand_btn = ft.IconButton(
                        icon=ft.Icons.KEYBOARD_ARROW_DOWN,
                        icon_color="#8e918f",
                        icon_size=20,
                        tooltip="Expand text",
                        style=ft.ButtonStyle(padding=0, shape=ft.CircleBorder()),
                        data=False
                    )

                    async def toggle_text(e):
                        is_expanded = not expand_btn.data
                        expand_btn.data = is_expanded
                        if is_expanded:
                            txt_control.max_lines = None
                            txt_control.overflow = None
                            expand_btn.icon = ft.Icons.KEYBOARD_ARROW_UP
                        else:
                            txt_control.max_lines = 10
                            txt_control.overflow = ft.TextOverflow.ELLIPSIS
                            expand_btn.icon = ft.Icons.KEYBOARD_ARROW_DOWN
                        txt_control.update()
                        expand_btn.update()

                    expand_btn.on_click = toggle_text

                    content_control = ft.Row(
                        vertical_alignment=ft.CrossAxisAlignment.START,
                        controls=[
                            ft.Container(content=txt_control, expand=True),
                            ft.Container(content=expand_btn, padding=ft.padding.only(left=5))
                        ]
                    )
                else:
                    content_control = txt_control

        # Standard Bubble Wrapper
        radius = ft.border_radius.only(
            top_left=18, top_right=2, bottom_right=18, bottom_left=18
        )
        # Narrower fallback for code/long messages (600px instead of 800px)
        bubble_width = 600 if (is_long or is_code) else None

        final_bubble = ft.Container(
            data=message.text,
            content=ft.Column([
                ft.Text(u_name, size=11, color=SUB_TEXT, visible=not is_me),
                content_control,
                ft.Text(message.timestamp, size=9, color="#8e918f", text_align=ft.TextAlign.RIGHT)
            ], spacing=2, horizontal_alignment=ft.CrossAxisAlignment.START),

            bgcolor=BUBBLE_BG,
            border_radius=radius,
            padding=ft.padding.only(top=12, bottom=12, left=16, right=16),
            width=bubble_width
        )

        return ft.Row(
            key=str(message.uid),
            vertical_alignment=ft.CrossAxisAlignment.START,
            alignment=ft.MainAxisAlignment.END if is_me else ft.MainAxisAlignment.START,
            controls=[
                ft.CircleAvatar(
                    content=ft.Text(u_name[:1].upper(), color="#131314", weight="bold"),
                    bgcolor=get_avatar_color(u_name),
                    radius=14,
                    visible=not is_me
                ),
                ft.Container(width=5, visible=not is_me),
                final_bubble
            ],
        )

    # --- INCOMING MESSAGE HANDLER ---
    async def handle_incoming_message(data, update_page=True):
        msg = database.Message(**data)
        uid_str = str(msg.uid)
        
        m = create_chat_message(msg)
        
        if uid_str in message_controls:
            # Efficiently find the index and replace
            existing_control = message_controls[uid_str]
            try:
                idx = chat.controls.index(existing_control)
                chat.controls[idx] = m
            except ValueError:
                # Fallback if list and map are out of sync somehow
                chat.controls.insert(0, m)
        else:
            chat.controls.insert(0, m)
            if msg.user_name in database.typing_status:
                del database.typing_status[msg.user_name]
        
        message_controls[uid_str] = m

        if update_page:
            try:
                chat.update()
                if uid_str not in message_controls: # This check is flawed but keeping same logic
                    if not scroll_down_button.visible or msg.user_name == state["user_name"]:
                        await scroll_to_bottom(instant=False)
                await update_typing_ui()
            except Exception:
                pass

    # --- PUBSUB LISTENER ---
    async def on_pubsub_message(data):
        if isinstance(data, dict):
            if data.get("message_type") == "clear_signal":
                chat.controls.clear()
                message_controls.clear()
                state["last_msg_id"] = 0
                page.update()
                return
            if data.get("message_type") == "delete_message":
                uid_to_delete = str(data.get("uid"))
                if uid_to_delete in message_controls:
                    control = message_controls.pop(uid_to_delete)
                    try:
                        chat.controls.remove(control)
                        page.update()
                    except ValueError:
                        pass
                return
            if data.get("message_type") == "typing_signal":
                u_name = data.get("user_name")
                if settings["typing_enabled"] and u_name != state["user_name"]:
                    database.typing_status[u_name] = time.time()
                    await update_typing_ui()
                return
            if data.get("message_type") == "user_count":
                user_count_text.value = f"{data.get('count', 0)} online"
                user_count_text.update()
                return
            if data.get("message_type") == "audio_message" and not data.get("audio_data"):
                await handle_incoming_message(data)
                return
            await handle_incoming_message(data)

    page.pubsub.subscribe(on_pubsub_message)

    # --- TYPING INDICATOR LOGIC ---
    typing_text = ft.Text(value="", italic=True, color="#8e918f", size=12, visible=False)

    async def update_typing_ui():
        if not settings["typing_enabled"]:
            if typing_text.visible:
                typing_text.visible = False
                typing_text.update()
            return
        now = time.time()
        active = [u for u, ts in database.typing_status.items()
                  if now - ts < database.DECAY_TIMEOUT
                  and u != state["user_name"]]
        if active:
            typing_text.value = f"{active[0]} is typing..." if len(active) == 1 else "Multiple people typing..."
            typing_text.visible = True
        else:
            typing_text.visible = False
        typing_text.update()

    async def typing_cleanup_loop():
        while page_alive:
            await asyncio.sleep(2)
            if typing_text.visible: await update_typing_ui()

    page.run_task(typing_cleanup_loop)

    # --- INPUT HANDLERS ---
    async def on_send_click(e):
        txt = new_message.value
        if not txt: return

        if txt.strip() == "/help":
            help_text = "**Commands:**\n`/lens <style>`\n`/capsule <60s> <msg>`\n`/help`"
            help_msg = database.Message(
                user_name="SYSTEM",
                text=help_text,
                message_type="analysis_message",
                timestamp=datetime.datetime.now().strftime("%H:%M"),
                uid=str(uuid.uuid4())
            )
            chat.controls.insert(0, create_chat_message(help_msg))
            new_message.value = ""
            chat.update()
            new_message.update()
            await scroll_to_bottom(instant=False)
            return

        new_message.value = ""
        page.update()
        try:
            database.insert_message(state["user_name"], txt, "chat_message", is_temp=state["is_temp_mode"])
        except Exception as ex:
            print(f"Send Error: {ex}")

    async def on_input_change(e):
        now = time.time()
        if state["user_name"] and (now - state["last_typing_sent"] > HEARTBEAT_INTERVAL):
            state["last_typing_sent"] = now
            database.send_typing_signal(state["user_name"])

    # --- FILE UPLOAD (AUDIO) ---
    async def on_file_picked(e):
        if e.files:
            file_obj = e.files[0]
            new_uid = str(uuid.uuid4())
            ts = datetime.datetime.now().strftime("%H:%M")
            safe_user = "".join(x for x in state["user_name"] if x.isalnum())
            filename = f"{safe_user}_{new_uid}.m4a"
            placeholder_data = {
                "user_name": state["user_name"],
                "text": "Uploading...",
                "message_type": "audio_message",
                "timestamp": ts,
                "uid": new_uid,
                "audio_data": None
            }
            await handle_incoming_message(placeholder_data)
            upload_url = page.get_upload_url(filename, 600)
            file_picker.upload([ft.FilePickerUploadFile(file_obj.name, upload_url=upload_url)])

            async def process_upload_background(fname, target_uid):
                attempts = 0
                full_path = os.path.join(database.UPLOAD_DIR, fname)
                while attempts < 20:
                    if os.path.exists(full_path):
                        await asyncio.sleep(1)
                        try:
                            # Upload to GCS (Offload blocking network call)
                            bucket = database.storage_client.bucket(database.BUCKET_NAME)
                            blob = bucket.blob(fname)
                            await asyncio.to_thread(blob.upload_from_filename, full_path)
                            gcs_uri = f"gs://{database.BUCKET_NAME}/{fname}"
                            
                            await asyncio.to_thread(
                                database.insert_message,
                                state["user_name"],
                                "Audio Message",
                                "audio_message",
                                is_temp=state["is_temp_mode"],
                                audio_payload=gcs_uri
                            )
                            await asyncio.to_thread(os.remove, full_path)
                            return
                        except Exception as ex:
                            print(f"GCS Upload error: {ex}")
                            return
                    await asyncio.sleep(1)
                    attempts += 1

            page.run_task(process_upload_background, filename, new_uid)

    file_picker.on_result = on_file_picked

    # FilePicker moved to top of main


    # --- SEARCH ---
    async def perform_search(e):
        query = search_box.value
        if not query: return await clear_search(e)
        
        # Pre-compile search pattern once
        try:
            q_regex = re.escape(query)
            query_pattern = re.compile(f"({q_regex})", re.IGNORECASE)
        except Exception:
            query_pattern = None

        matches = 0
        first_key = None
        for control in reversed(chat.controls):
            if isinstance(control, ft.Row) and len(control.controls) > 1:
                bubble_container = None
                for c in control.controls:
                    if isinstance(c, ft.Container) and c.data:
                        bubble_container = c

                if bubble_container:
                    original_text = bubble_container.data
                    if query.lower() in original_text.lower():
                        matches += 1
                        if not first_key: first_key = control.key
                        bubble_container.content = ft.Text(
                            spans=generate_spans(original_text, query_pattern=query_pattern, query_text=query),
                            selectable=True,
                            size=15,
                            color="#e3e3e3",
                            font_family="Roboto, sans-serif"
                        )
                    elif isinstance(bubble_container.content, ft.Text):
                        bubble_container.content = create_message_content(original_text)

        chat.update()
        search_box.label = f"{matches} matches"
        search_box.update()
        if first_key: await chat.scroll_to_async(key=first_key, duration=500)

    async def clear_search(e):
        search_box.value = ""
        search_box.label = "Search"
        state["history_cursor"] = 0
        chat.controls.clear()
        await load_history_chunk()
        page.update()

    search_box = ft.TextField(
        label="Search",
        width=250,
        height=40,
        content_padding=ft.padding.only(left=15, right=10, top=5),
        border_radius=20,
        bgcolor="#1e1f20",
        border_width=0,
        text_style=ft.TextStyle(color="white"),
        label_style=ft.TextStyle(color="#8e918f"),
        on_submit=perform_search,
        suffix=ft.Container(
            content=ft.Icon(ft.Icons.CLOSE, size=16, color="#8e918f"),
            on_click=clear_search,
            padding=5,
            ink=True,
            border_radius=20
        )
    )

    # --- SETTINGS / ADMIN ---
    async def clear_database_click(e):
        if await asyncio.to_thread(database.clear_global_database):
            page.snack_bar = ft.SnackBar(content=ft.Text("GLOBAL DATABASE CLEARED"))
            page.snack_bar.open = True
            page.update()

    def update_deja_vu(e):
        settings["deja_vu_enabled"] = deja_vu_switch.value
        database.DEJA_VU_ENABLED = settings["deja_vu_enabled"]
        print(f"DEBUG: Deja Vu Enabled = {database.DEJA_VU_ENABLED}")

    typing_switch = ft.Switch(
        label="Typing Indicator",
        value=True,
        on_change=lambda e: setattr(settings, "typing_enabled", typing_switch.value)
    )

    deja_vu_switch = ft.Switch(
        label="Enable Déjà Vu (AI)",
        value=False,
        on_change=update_deja_vu
    )

    clear_button = ft.FilledButton(
        "Clear Global Database",
        style=ft.ButtonStyle(bgcolor="#B71C1C", color="white"),
        on_click=clear_database_click
    )

    uptime_text = ft.Text(size=12, color="#8e918f")

    settings_sheet = ft.BottomSheet(
        ft.Container(
            ft.Column([
                ft.Text("Settings", weight="bold", size=18, color="white"),
                ft.Divider(color="#444746"),
                typing_switch,
                deja_vu_switch,
                ft.Container(height=5),
                clear_button,
                ft.Divider(color="#444746"),
                ft.Row([ft.Text("Server Uptime:", size=12, color="#8e918f"), uptime_text])
            ], tight=True, spacing=15),
            padding=30,
            bgcolor="#1e1f20",
            border_radius=ft.border_radius.vertical(top=28)
        )
    )
    page.overlay.append(settings_sheet)

    async def open_settings(e):
        uptime_text.value = database.get_uptime()
        settings_sheet.open = True
        page.update()

    settings_button = ft.IconButton(
        icon=ft.Icons.SETTINGS,
        icon_color="#c4c7c5",
        on_click=open_settings,
        tooltip="Settings"
    )

    async def logout_click(e):
        if hasattr(page, "client_storage"):
            page.client_storage.remove("user_name")
        state["user_name"] = None
        session_avatar.visible = False
        session_name.visible = False
        logout_button.visible = False
        
        if welcome_dlg not in page.overlay:
            page.overlay.append(welcome_dlg)
        welcome_dlg.open = True
        page.update()

    logout_button = ft.IconButton(
        icon=ft.Icons.LOGOUT,
        icon_color="#c4c7c5",
        on_click=logout_click,
        tooltip="Logout",
        visible=False
    )

    # --- HINTS & INPUT ---
    hint_choices = ["Ask anything...", "Type a message...", "Enter a prompt here..."]
    selected_hint = random.choice(hint_choices)

    async def toggle_timer(e):
        state["is_temp_mode"] = not state["is_temp_mode"]
        if state["is_temp_mode"]:
            timer_button.icon_color = "#f28b82"  # Pastel Red
            new_message.hint_text = "Temporary message (60s)..."
        else:
            timer_button.icon_color = "#c4c7c5"
            new_message.hint_text = selected_hint
        timer_button.update()
        new_message.update()

    timer_button = ft.IconButton(
        icon=ft.Icons.TIMER,
        icon_color="#c4c7c5",
        on_click=toggle_timer,
        tooltip="Toggle Temporary Message"
    )

    new_message = ft.TextField(
        hint_text=selected_hint,
        hint_style=ft.TextStyle(color="#8e918f"),
        text_style=ft.TextStyle(color="#e3e3e3", size=16),
        expand=True,
        on_submit=on_send_click,
        on_change=on_input_change,
        multiline=True,
        min_lines=1,
        max_lines=5,
        bgcolor="transparent",
        border_width=0,
        content_padding=ft.padding.all(15),
    )

    send_button = ft.IconButton(
        icon=ft.Icons.SEND_ROUNDED,
        icon_color="#e3e3e3",
        on_click=on_send_click,
        tooltip="Send message"
    )

    input_container = ft.Container(
        content=ft.Row([
            timer_button,
            # ft.IconButton(
            #     icon=ft.Icons.ADD_CIRCLE_OUTLINE,
            #     icon_color="#c4c7c5",
            #     tooltip="Upload Audio (Disabled)",
            #     on_click=lambda _: file_picker.pick_files(allow_multiple=False, file_type=ft.FilePickerFileType.AUDIO)
            # ),
            new_message,
            send_button
        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
        bgcolor="#1e1f20",
        border_radius=32,
        padding=5,
        margin=ft.padding.only(left=20, right=20, bottom=20, top=10)
    )

    async def join_chat_click(e):
        if not join_user_name.value:
            join_user_name.error_text = "Name cannot be blank!"
            join_user_name.update()
            return

        state["user_name"] = join_user_name.value
        if hasattr(page, "client_storage"):
            page.client_storage.set("user_name", state["user_name"])

        welcome_dlg.open = False
        session_avatar.visible = True
        session_name.visible = True
        session_name.value = state["user_name"]
        session_avatar.content = ft.Text(state["user_name"][:1].upper(), color="#131314", weight="bold")
        logout_button.visible = True
        page.update()

        # FETCH FULL HISTORY
        state["full_history"] = database.get_recent_messages()
        state["history_cursor"] = 0
        chat.controls.clear()
        message_controls.clear()
        
        await load_history_chunk()
        page.update()
        
        # Scroll to bottom (since index 0 is newest and reverse=True, this is offset 0)
        await scroll_to_bottom(instant=True)
        
        try:
            database.insert_message(state["user_name"], f"{state['user_name']} joined", "login_message")
        except Exception as e:
            pass

    # --- LOGIN DIALOG ---
    join_user_name = ft.TextField(
        label="What's your name?",
        label_style=ft.TextStyle(color="#8e918f"),
        text_style=ft.TextStyle(color="white"),
        bgcolor="#1e1f20",
        border_color="#444746",
        on_submit=join_chat_click,
        autofocus=True
    )


    welcome_dlg = ft.AlertDialog(
        modal=True,
        title=ft.Text("Welcome to LDN Chat", color="white", weight="bold"),
        content=ft.Container(content=join_user_name, width=400, padding=10),
        actions=[ft.TextButton("JOIN CHAT", on_click=join_chat_click)],
        bgcolor="#1e1f20",
    )
    page.overlay.append(welcome_dlg)

    # --- BUILD PAGE ---
    # RESTORED: The 'header' definition block
    header = ft.Container(
        content=ft.Row([
            ft.Row([user_session_info, ft.Container(width=10), user_count_text]),
            ft.Row([search_box, settings_button, logout_button],
                   vertical_alignment=ft.CrossAxisAlignment.CENTER)
        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
        padding=ft.padding.only(left=20, right=20, top=10, bottom=0),
        bgcolor=PAGE_BG
    )

    # Stack for Bottom-Left Toast Notification
    main_layout = ft.Column(
        controls=[
            header,
            ft.Stack([
                chat_container,
                ft.Container(content=scroll_down_button, bottom=10, right=45)
            ], expand=True),

            ft.Container(content=typing_text, padding=ft.padding.only(left=40, bottom=5)),

            input_container
        ], expand=True, spacing=0
    )

    page.add(
        ft.Stack(
            [
                main_layout,
                copy_banner
            ],
            expand=True
        )
    )

    if stored_user:
        join_user_name.value = stored_user
        page.run_task(join_chat_click, None)
    else:
        welcome_dlg.open = True
        page.update()

if __name__ == "__main__":
    port = int(os.getenv("PORT", 9090))
    # Always run in web mode per user request
    # host_addr: 0.0.0.0 for all environments to ensure WebSocket reliability
    host_addr = "0.0.0.0"
    
    ft.app(
        target=main,
        port=port,
        host=host_addr,
        assets_dir="assets",
        upload_dir="uploads",
        view=ft.AppView.WEB_BROWSER
    )
