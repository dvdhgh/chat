# LDN Chat Version: v3.10.5 (Layout Tweaks)
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
import ui_components as ui
# import flet_audio as fta # Temporarily disabled to isolate conflicts

print(f"DEBUG: Startup - Flet Version: {ft.__version__}")
APP_VERSION = "v3.10.5 (Layout Tweaks)"
# --- CONFIG ---
HEARTBEAT_INTERVAL = 4.0
HISTORY_BATCH_SIZE = 30


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
        "is_loading_history": False,
        "last_search_query": ""
    }

    # Optimization: O(1) lookup for message controls
    message_controls = {}

    # --- SETUP PAGE ---
    page.theme_mode = ft.ThemeMode.DARK
    page.bgcolor = ui.PAGE_BG
    page.title = f"LDN Chat {APP_VERSION}"
    page.padding = 0

    file_picker = ft.FilePicker()

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
    session_name = ft.Text(value="", weight="bold", visible=False, color=ui.TEXT_COLOR)
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
        bgcolor=ui.PAGE_BG,
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
                m = ui.create_chat_message(
                    msg, 
                    state["user_name"], 
                    trigger_copy_callback=lambda c: page.run_task(trigger_copy_snack, c),
                    on_tap_link=page.launch_url,
                    play_audio_callback=play_audio_message
                )
                if m:
                    message_controls[str(msg.uid)] = m
                    new_controls.append(m)
            except Exception as e:
                print(f"DEBUG: Error creating message {msg.uid}: {e}")

        print(f"DEBUG: load_history_chunk - adding {len(new_controls)} controls to chat.")
        chat.controls.extend(new_controls)
        
        # DOM CAPPING: Limit to 200 messages to maintain mobile performance
        if len(chat.controls) > 200:
            chat.controls = chat.controls[:200]

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

    # --- INCOMING MESSAGE HANDLER ---
    async def handle_incoming_message(data, update_page=True):
        msg = database.Message(**data)
        uid_str = str(msg.uid)
        
        m = ui.create_chat_message(
            msg, 
            state["user_name"], 
            trigger_copy_callback=lambda c: page.run_task(trigger_copy_snack, c),
            on_tap_link=page.launch_url,
            play_audio_callback=play_audio_message
        )
        
        if uid_str in message_controls:
            existing_control = message_controls[uid_str]
            try:
                idx = chat.controls.index(existing_control)
                chat.controls[idx] = m
            except ValueError:
                chat.controls.insert(0, m)
        else:
            chat.controls.insert(0, m)
            if msg.user_name in database.typing_status:
                del database.typing_status[msg.user_name]

        # DOM CAPPING: Ensure the list doesn't grow indefinitely on mobile
        if len(chat.controls) > 200:
            removed = chat.controls.pop() # Remove oldest from the end
            # Cleanup message_controls to prevent memory leak
            if hasattr(removed, 'key') and removed.key in message_controls:
                del message_controls[removed.key]
        
        message_controls[uid_str] = m

        if update_page:
            try:
                chat.update()
                # Scroll to bottom if user is at the bottom or it's their own message
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
            chat.controls.insert(0, ui.create_chat_message(
                help_msg, 
                state["user_name"], 
                trigger_copy_callback=lambda c: page.run_task(trigger_copy_snack, c),
                on_tap_link=page.launch_url,
                play_audio_callback=play_audio_message
            ))
            new_message.value = ""
            chat.update()
            new_message.update()
            await scroll_to_bottom(instant=False)
            return

        new_message.value = ""
        page.update()
        try:
            print(f"DEBUG: App sending message. text={txt[:20]}..., is_temp={state['is_temp_mode']}")
            # Use to_thread to prevent blocking the UI loop
            await asyncio.to_thread(database.insert_message, state["user_name"], txt, "chat_message", is_temp=state["is_temp_mode"])

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

    # --- SEARCH OPTIMIZED ---
    async def perform_search(e):
        query = search_box.value
        if not query: return await clear_search(e)
        
        # Optimization: Don't re-run if query is identical
        if query == state["last_search_query"]:
            return
        state["last_search_query"] = query

        # Pre-compile search pattern once
        try:
            q_regex = re.escape(query)
            query_pattern = re.compile(f"({q_regex})", re.IGNORECASE)
        except Exception:
            query_pattern = None

        matches = 0
        first_key = None
        processed_count = 0
        
        for control in reversed(chat.controls):
            processed_count += 1
            if processed_count % 10 == 0:
                await asyncio.sleep(0) # Yield for UI responsiveness

            if isinstance(control, ft.Row) and len(control.controls) > 1:
                bubble_container = None
                for c in control.controls:
                    if isinstance(c, ft.Container) and c.data:
                        bubble_container = c

                if bubble_container:
                    original_text = bubble_container.data
                    is_match = query.lower() in original_text.lower()
                    
                    if is_match:
                        matches += 1
                        if not first_key: first_key = control.key
                        bubble_container.content = ft.Text(
                            spans=ui.generate_spans(original_text, page.launch_url, query_pattern=query_pattern, query_text=query),
                            selectable=True,
                            size=15,
                            color="#e3e3e3",
                            font_family="Roboto, sans-serif"
                        )
                    else:
                        # Selective re-rendering: Only revert if it was previously highlighted
                        # This avoids expensive Markdown re-builds for non-matches
                        if isinstance(bubble_container.content, ft.Text) and bubble_container.content.spans:
                            bubble_container.content = ui.create_message_content(
                                original_text,
                                trigger_copy_callback=lambda c: page.run_task(trigger_copy_snack, c),
                                on_tap_link=page.launch_url
                            )

        chat.update()
        search_box.label = f"{matches} matches"
        search_box.update()
        try:
            if first_key: await chat.scroll_to(offset=0, duration=500)
        except Exception as ex:
            print(f"Search scroll failed: {ex}")

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
                ft.Divider(color="#444746"),
                ft.Text("Administrative", weight="bold", color="#8e918f"),
                clear_button,
                uptime_text
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
        tooltip="Settings",
        scale=0.9
    )


    async def logout_click(e):
        if hasattr(page, "client_storage"):
            page.client_storage.remove("user_name")
        state["user_name"] = None
        session_avatar.visible = False
        session_name.visible = False
        logout_button.visible = False
        
        page.dialog = welcome_dlg
        welcome_dlg.open = True
        page.update()

    logout_button = ft.IconButton(
        icon=ft.Icons.LOGOUT,
        icon_color="#c4c7c5",
        on_click=logout_click,
        tooltip="Logout",
        visible=False,
        scale=0.9
    )


    # --- HINTS & INPUT ---
    hint_choices = ["Ask anything...", "Type a message...", "Enter a prompt here..."]
    selected_hint = random.choice(hint_choices)

    async def toggle_timer(e):
        state["is_temp_mode"] = not state["is_temp_mode"]
        print(f"DEBUG: Toggle Timer: is_temp_mode={state['is_temp_mode']}")
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
        text_style=ft.TextStyle(color=ui.TEXT_COLOR, size=16),
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

        # FETCH FULL HISTORY in background
        state["full_history"] = await asyncio.to_thread(database.get_recent_messages)
        state["history_cursor"] = 0
        chat.controls.clear()
        message_controls.clear()
        
        await load_history_chunk()
        page.update()
        
        # Scroll to bottom (since index 0 is newest and reverse=True, this is offset 0)
        await scroll_to_bottom(instant=True)
        
        try:
            await asyncio.to_thread(database.insert_message, state["user_name"], f"{state['user_name']} joined", "login_message")
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
    page.dialog = welcome_dlg

    # --- PAGE RESPONSIVENESS ---
    def on_page_resize(e):
        is_mobile = page.width < 600
        search_box.visible = not is_mobile
        mobile_search_btn.visible = is_mobile
        if is_mobile:
            user_count_text.size = 10
            session_name.visible = page.width > 400
        else:
            user_count_text.size = 12
            session_name.visible = True
        page.update()

    page.on_resize = on_page_resize

    async def toggle_mobile_search(e):
        search_box.visible = not search_box.visible
        if search_box.visible:
            mobile_search_btn.icon = ft.Icons.CLOSE
            user_session_info.visible = False
            user_count_text.visible = False
            search_box.focus() # Ensure it's ready to type
        else:
            mobile_search_btn.icon = ft.Icons.SEARCH
            user_session_info.visible = True
            user_count_text.visible = True
        page.update()

    mobile_search_btn = ft.IconButton(
        icon=ft.Icons.SEARCH,
        icon_color="#c4c7c5",
        visible=False,
        on_click=toggle_mobile_search,
        scale=0.9
    )

    # --- BUILD PAGE ---
    header = ft.Container(
        content=ft.Row([
            ft.Row([user_session_info, ft.Container(width=5), user_count_text], 
                   alignment=ft.MainAxisAlignment.START, tight=True, expand=True),
            ft.Row([
                mobile_search_btn,
                search_box,
                settings_button,
                logout_button
            ], alignment=ft.MainAxisAlignment.END, tight=True)
        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
        padding=ft.padding.only(left=10, right=10, top=10, bottom=0),
        bgcolor=ui.PAGE_BG,
        height=50 # Explicit height to ensure it doesn't jump
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
        page.dialog = welcome_dlg
        welcome_dlg.open = True
        page.update()

if __name__ == "__main__":
    port = int(os.getenv("PORT", 9090))
    # Always run in web mode per user request
    # host_addr: 0.0.0.0 for Cloud Run, 127.0.0.1 (localhost) for local development
    host_addr = "0.0.0.0" if os.getenv("K_SERVICE") else "127.0.0.1"
    
    ft.app(
        target=main,
        port=port,
        host=host_addr,
        assets_dir="assets",
        upload_dir="uploads",
        view=ft.AppView.WEB_BROWSER
    )
