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
    await asyncio.to_thread(database.init_db) # Idempotent call
    
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
            # Refresh message_controls mapping for consistency if needed
            # (In reverse mode, index 0 is bottom, so we remove from the end/top)

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

    # Removed UI rendering logic (moved to ui_components.py)

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
            # Update existing
            old_control = message_controls[uid_str]
            idx = chat.controls.index(old_control)
            chat.controls[idx] = m
            message_controls[uid_str] = m
        else:
            # Add new
            chat.controls.insert(0, m)
            message_controls[uid_str] = m
            # If we were at the bottom (offset 0), stay at the bottom
            # Actually with reverse=True, adding to index 0 is adding to the bottom
            
            # DOM CAPPING
            if len(chat.controls) > 200:
                chat.controls = chat.controls[:200]

        if update_page:
            chat.update()
            page.update()

    # --- PUBSUB HANDLER ---
    async def on_broadcast(data):
        if not page_alive: return

        m_type = data.get("message_type")
        
        if m_type == "clear_signal":
            chat.controls.clear()
            message_controls.clear()
            chat.update()
            page.update()
            return

        if m_type == "delete_message":
            uid = data.get("uid")
            if uid in message_controls:
                ctrl = message_controls.pop(uid)
                if ctrl in chat.controls:
                    chat.controls.remove(ctrl)
                    chat.update()
                    page.update()
            return

        if m_type == "typing_signal":
            u_name = data.get("user_name")
            if u_name == state["user_name"]: return
            
            database.typing_status[u_name] = time.time()
            return

        # Handle Standard Messages (Chat, Analysis, System, Login)
        await handle_incoming_message(data)

    page.pubsub.on_message = on_broadcast

    # --- SEARCH LOGIC ---
    search_results = []
    search_cursor = 0
    search_active = False

    async def execute_search(query):
        nonlocal search_active, search_results, search_cursor
        query = query.lower().strip()
        state["last_search_query"] = query
        
        if not query:
            search_active = False
            search_results = []
            # Restore normal view
            chat.controls.clear()
            message_controls.clear()
            state["history_cursor"] = 0
            await load_history_chunk()
            await scroll_to_bottom(instant=True)
            return

        search_active = True
        # Filter from FULL history (local)
        search_results = [m for m in state["full_history"] if query in m.text.lower() or query in m.user_name.lower()]
        
        chat.controls.clear()
        message_controls.clear()
        
        # Display first batch of results
        display_count = min(len(search_results), HISTORY_BATCH_SIZE)
        for i in range(display_count):
            msg = search_results[i]
            m = ui.create_chat_message(
                msg, 
                state["user_name"], 
                trigger_copy_callback=lambda c: page.run_task(trigger_copy_snack, c),
                on_tap_link=page.launch_url,
                play_audio_callback=play_audio_message
            )
            chat.controls.append(m)
            message_controls[str(msg.uid)] = m
            
        chat.update()
        page.update()

    async def on_search_change(e):
        # We use a small delay to avoid thrashing during typing
        await asyncio.sleep(0.3)
        if e.control.value == state["last_search_query"]:
            await execute_search(e.control.value)

    search_box = ft.TextField(
        hint_text="Search messages...",
        prefix_icon=ft.Icons.SEARCH,
        on_change=on_search_change,
        bgcolor="#1e1f20",
        border_radius=20,
        border_color="transparent",
        height=40,
        content_padding=ft.padding.only(left=15, right=10, top=5),
        text_size=14,
        expand=True,
        visible=True # Visible by default on desktop
    )

    # --- SETTINGS MENU ---
    async def update_deja_vu(e):
        settings["deja_vu_enabled"] = deja_vu_switch.value
        database.DEJA_VU_ENABLED = settings["deja_vu_enabled"]
        print(f"DEBUG: settings - Deja Vu set to: {database.DEJA_VU_ENABLED}")

    async def clear_database_click(e):
        def on_confirm(ce):
            confirm_dlg.open = False
            page.update()
            if database.clear_global_database():
                print("DEBUG: Database cleared.")

        confirm_dlg = ft.AlertDialog(
            title=ft.Text("Clear Database?"),
            content=ft.Text("This will delete ALL messages for everyone. Are you sure?"),
            actions=[
                ft.TextButton("Cancel", on_click=lambda _: setattr(confirm_dlg, "open", False)),
                ft.TextButton("Yes, Clear Everything", on_click=on_confirm, style=ft.ButtonStyle(color="#B71C1C"))
            ]
        )
        page.overlay.append(confirm_dlg)
        confirm_dlg.open = True
        page.update()

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

    async def logout_click(e):
        if hasattr(page, "client_storage"):
            page.client_storage.remove("user_name")
        state["user_name"] = None
        session_avatar.visible = False
        session_name.visible = False
        logout_button.visible = False
        
        # Disable input when logged out
        new_message.disabled = True
        send_button.disabled = True
        
        settings_sheet.open = False
        welcome_dlg.open = True
        page.update()

    logout_button = ft.ElevatedButton(
        "Logout",
        icon=ft.Icons.LOGOUT,
        on_click=logout_click,
        style=ft.ButtonStyle(color="white", bgcolor="#D32F2F"),
        visible=True
    )

    async def open_settings(e):
        uptime_text.value = database.get_uptime()
        settings_sheet.open = True
        page.update()

    settings_sheet = ft.BottomSheet(
        ft.Container(
            ft.Column([
                ft.Text("Settings", weight="bold", size=18, color="white"),
                ft.Divider(color="#444746"),
                typing_switch,
                deja_vu_switch,
                ft.Divider(color="#444746"),
                logout_button,
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

    settings_button = ft.IconButton(
        icon=ft.Icons.SETTINGS,
        icon_color="#c4c7c5",
        on_click=open_settings,
        tooltip="Settings",
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
        expand=True,
        border_radius=24,
        bgcolor="#1e1f20",
        border_color="transparent",
        on_submit=lambda e: page.run_task(send_click, e),
        on_change=lambda e: page.run_task(on_typing, e),
        content_padding=ft.padding.all(15),
        text_size=16,
        multiline=True,
        min_lines=1,
        max_lines=5,
        shift_enter=True
    )

    async def on_typing(e):
        if not settings["typing_enabled"]: return
        now = time.time()
        if now - state["last_typing_sent"] > 2.0:
            state["last_typing_sent"] = now
            # Offload heavy DB write to background 
            await asyncio.to_thread(database.send_typing_signal, state["user_name"])

    async def send_click(e):
        if not new_message.value: return
        text = new_message.value
        new_message.value = ""
        new_message.update()
        
        # Offload Firestore insertion to thread
        await asyncio.to_thread(
            database.insert_message, 
            state["user_name"], 
            text, 
            "chat_message", 
            is_temp=state["is_temp_mode"]
        )
        await scroll_to_bottom()

    send_button = ft.IconButton(
        icon=ft.Icons.SEND_ROUNDED,
        icon_color="#8ab4f8",
        on_click=lambda e: page.run_task(send_click, e)
    )

    input_container = ft.Container(
        content=ft.Row([
            timer_button,
            new_message,
            send_button
        ], alignment=ft.MainAxisAlignment.CENTER),
        padding=0,
        margin=ft.padding.only(left=20, right=20, bottom=20, top=10)
    )

    # --- TYPING INDICATOR LOOP ---
    typing_text = ft.Text(value="", size=12, italic=True, color="#8e918f", animate_opacity=200)

    async def update_typing_ui():
        while page_alive:
            try:
                now = time.time()
                active_typers = [u for u, t in database.typing_status.items() if now - t < database.DECAY_TIMEOUT]
                
                if not active_typers:
                    typing_text.value = ""
                    typing_text.opacity = 0
                elif len(active_typers) == 1:
                    typing_text.value = f"{active_typers[0]} is typing..."
                    typing_text.opacity = 1
                else:
                    typing_text.value = "Multiple people are typing..."
                    typing_text.opacity = 1
                
                typing_text.update()
            except:
                pass
            await asyncio.sleep(1.0)

    page.run_task(update_typing_ui)

    # --- HEARTBEAT & SYNC ---
    async def heartbeat_loop():
        while page_alive:
            try:
                # 1. Update User Count
                active_users = database.get_active_user_count()
                user_count_text.value = f"● {active_users} online"
                user_count_text.update()
            except:
                pass
            await asyncio.sleep(HEARTBEAT_INTERVAL)

    page.run_task(heartbeat_loop)

    async def join_chat_click(e):
        try:
            print(f"DEBUG: join_chat_click starting for {join_user_name.value}")
            if not join_user_name.value:
                join_user_name.error_text = "Name cannot be blank!"
                join_user_name.update()
                return

            state["user_name"] = join_user_name.value
            if hasattr(page, "client_storage"):
                page.client_storage.set("user_name", state["user_name"])

            welcome_dlg.open = False
            
            # Enable input when logged in
            new_message.disabled = False
            send_button.disabled = False
            
            session_avatar.visible = True
            session_name.visible = True
            session_name.value = state["user_name"]
            session_avatar.content = ft.Text(state["user_name"][:1].upper(), color="#131314", weight="bold")
            logout_button.visible = True
            page.update()

            # FETCH FULL HISTORY in background
            print("DEBUG: join_chat_click fetching history...")
            state["full_history"] = await asyncio.to_thread(database.get_recent_messages)
            state["history_cursor"] = 0
            chat.controls.clear()
            message_controls.clear()
            
            print("DEBUG: join_chat_click loading chunk...")
            await load_history_chunk()
            page.update()
            
            # Scroll to bottom (since index 0 is newest and reverse=True, this is offset 0)
            await scroll_to_bottom(instant=True)
            
            try:
                await asyncio.to_thread(database.insert_message, state["user_name"], f"{state['user_name']} joined", "login_message")
            except Exception as e:
                print(f"DEBUG: Join notification error: {e}")
            print("DEBUG: join_chat_click finished.")
        except Exception as e:
            print(f"CRITICAL: join_chat_click FAILED: {e}")
            import traceback
            traceback.print_exc()

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

    # --- PAGE RESPONSIVENESS ---
    def on_page_resize(e):
        is_mobile = page.width < 600
        search_box.visible = not is_mobile
        mobile_search_btn.visible = is_mobile
        if is_mobile:
            user_count_text.size = 10
            session_name.visible = (page.width > 400 and state["user_name"] is not None)
            session_avatar.visible = (state["user_name"] is not None)
        else:
            user_count_text.size = 12
            session_name.visible = state["user_name"] is not None
            session_avatar.visible = state["user_name"] is not None
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
                settings_button
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

    if stored_user and stored_user.strip():
        join_user_name.value = stored_user
        await join_chat_click(None)
    else:
        # Ensure input is disabled if not joined
        new_message.disabled = True
        send_button.disabled = True
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
