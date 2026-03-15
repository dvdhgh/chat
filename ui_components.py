# CRITICAL: Always prioritize mobile performance. 
# Use ft.Text instead of ft.Markdown for message content by default (Light Mode).
import flet as ft
import re
import database

# --- COLOR PALETTE ---
PAGE_BG = "#131314"  # The main dark background
CODE_BG = "#282c34"  # Matches 'ATOM_ONE_DARK' theme background
BUBBLE_BG = "#2A2A2A"  # Standard message bubble
TEXT_COLOR = "#e3e3e3"  # Main text
SUB_TEXT = "#c4c7c5"  # Secondary text (headers, names)

# --- PRE-COMPILED PATTERNS ---
URL_PATTERN = re.compile(r"((?:https?://|www\.)\S+)", re.IGNORECASE)

def generate_spans(text, on_link_click, query_pattern=None, query_text=None, active_match_index=None, current_match_counter=None):
    if current_match_counter is None:
        current_match_counter = [0]
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
                on_click=lambda e, u=url_to_open: on_link_click(u)
            ))
        else:
            if query_pattern and query_text and query_text.lower() in part.lower():
                sub_parts = query_pattern.split(part)
                for sub in sub_parts:
                    if not sub: continue
                    if sub.lower() == query_text.lower():
                        # Highlight logic
                        is_active = (active_match_index is not None and current_match_counter[0] == active_match_index)
                        bg_color = "#FFFFFF" if is_active else "#F9A825"
                        text_color = "black" if is_active else "white"
                        
                        spans.append(ft.TextSpan(
                            text=sub, 
                            style=ft.TextStyle(bgcolor=bg_color, color=text_color, weight="bold" if is_active else None)
                        ))
                        current_match_counter[0] += 1
                    else:
                        spans.append(ft.TextSpan(text=sub))
            else:
                spans.append(ft.TextSpan(text=part))
    return spans

def get_message_markdown(text, on_tap_link):
    return ft.Markdown(
        value=text,
        selectable=True,
        extension_set=ft.MarkdownExtensionSet.GITHUB_WEB,
        code_theme=ft.MarkdownCodeTheme.ATOM_ONE_DARK,
        on_tap_link=lambda e: on_tap_link(e.data),
    )

def create_message_content(text, trigger_copy_callback, on_tap_link):
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
                        on_click=lambda e: trigger_copy_callback(raw_code)
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
            return get_message_markdown(text, on_tap_link)

    return get_message_markdown(text, on_tap_link)

def create_chat_message(message: database.Message, current_user_name, trigger_copy_callback, on_tap_link, play_audio_callback, light_mode=True):
    u_name = message.user_name if message.user_name else "Unknown"
    is_me = u_name == current_user_name

    if message.message_type == "login_message":
        return ft.Row(
            key=str(message.uid),
            alignment=ft.MainAxisAlignment.CENTER,
            controls=[ft.Text(value=message.text, size=11, color="#8e918f", italic=True)]
        )

    if (message.message_type == "analysis_message" or u_name == "ARCHIVE"):
        if light_mode:
            content_control = ft.Text(
                value=f"--- {u_name} ANALYSIS ---\n{message.text}", 
                size=14, color=SUB_TEXT, selectable=True
            )
        else:
            return ft.Row(
                key=str(message.uid),
                vertical_alignment=ft.CrossAxisAlignment.START,
                controls=[
                    ft.Icon(ft.Icons.AUTO_AWESOME, color=SUB_TEXT, size=20),
                    ft.Container(width=10),
                    ft.Column(
                        expand=True,
                        controls=[create_message_content(message.text, trigger_copy_callback, on_tap_link)]
                    )
                ]
            )
    else:
        # Standard logic
        pass

    def get_avatar_color(user_name: str):
        if not user_name: user_name = "default"
        clist = ["#8ab4f8", "#81c995", "#f28b82", "#fdd663", "#c58af9", "#78d9ec"]
        return clist[hash(user_name) % len(clist)]

    content_control = None
    if message.message_type == "audio_message":
        if message.audio_data:
            async def on_play_click(e):
                await play_audio_callback(message.uid, message.audio_data)

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
        if light_mode:
            # PERFORMANCE MODE: Use simple text spans even for long/code messages
            content_control = ft.Text(
                spans=generate_spans(message.text, on_tap_link),
                selectable=True,
                size=15,
                color=TEXT_COLOR,
                font_family="Roboto, sans-serif"
            )
        else:
            is_code = message.text.strip().startswith("```")
            is_long = len(message.text) > 400 or message.text.count('\n') > 10
            is_markdown = any(char in message.text for char in ["*", "_", "`", "[", "#", "|"])

            if is_code:
                content_control = create_message_content(message.text, trigger_copy_callback, on_tap_link)
            elif is_markdown:
                content_control = get_message_markdown(message.text, on_tap_link)
            else:
                txt_control = ft.Text(
                    spans=generate_spans(message.text, on_tap_link),
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
    bubble_width = 600 if (not light_mode and (len(message.text) > 400 or message.text.count('\n') > 10 or message.text.strip().startswith("```"))) else None

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
        spacing=5, # Replaces the spacer container
        controls=[
            ft.CircleAvatar(
                content=ft.Text(u_name[:1].upper(), color="#131314", weight="bold"),
                bgcolor=get_avatar_color(u_name),
                radius=14,
                visible=not is_me
            ),
            final_bubble
        ],
    )
