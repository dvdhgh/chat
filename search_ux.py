import flet as ft
import re
import asyncio
import ui_components as ui

class SearchUX:
    def __init__(self, page, state, chat, trigger_copy_snack):
        self.page = page
        self.state = state
        self.chat = chat
        self.trigger_copy_snack = trigger_copy_snack
        
        self.search_box = ft.TextField(
            label="Search",
            width=300,
            height=40,
            content_padding=ft.padding.only(left=15, right=10, top=5),
            border_radius=20,
            bgcolor="#1e1f20",
            border_width=0,
            text_style=ft.TextStyle(color="white"),
            label_style=ft.TextStyle(color="#8e918f"),
            on_submit=self.perform_search,
            on_focus=lambda _: self.state.__setitem__("search_focused", True),
            on_blur=lambda _: self.state.__setitem__("search_focused", False),
            suffix=ft.Row([
                ft.IconButton(ft.Icons.KEYBOARD_ARROW_UP, icon_size=18, icon_color="#8e918f", 
                              on_click=lambda _: self.page.run_task(self.jump_to_match, self.state["active_search_index"] - 1)),
                ft.IconButton(ft.Icons.KEYBOARD_ARROW_DOWN, icon_size=18, icon_color="#8e918f", 
                              on_click=lambda _: self.page.run_task(self.jump_to_match, self.state["active_search_index"] + 1)),
                ft.IconButton(ft.Icons.CLOSE, icon_size=18, icon_color="#8e918f", on_click=self.clear_search),
            ], tight=True, spacing=0)
        )

    async def jump_to_match(self, index):
        if not self.state["search_matches"]: return
        
        # Wrap index
        index = index % len(self.state["search_matches"])
        self.state["active_search_index"] = index
        
        match = self.state["search_matches"][index]
        query = self.search_box.value
        try:
            q_regex = re.escape(query)
            query_pattern = re.compile(f"({q_regex})", re.IGNORECASE)
        except Exception: return

        # Re-render ONLY bubbles that are in search_matches to show active highlight
        temp_counter = [0]
        unique_bubbles = {}
        for m in self.state["search_matches"]:
            unique_bubbles[m["bubble"]] = m["text"]

        for bubble, text in unique_bubbles.items():
            bubble.content = ft.Text(
                spans=ui.generate_spans(
                    text, 
                    self.page.launch_url, 
                    query_pattern=query_pattern, 
                    query_text=query, 
                    active_match_index=index, 
                    current_match_counter=temp_counter
                ),
                selectable=True,
                size=15,
                color=ui.TEXT_COLOR,
                font_family="Roboto, sans-serif"
            )

        self.search_box.label = f"{index + 1} of {len(self.state['search_matches'])}"
        self.search_box.update()
        self.chat.update()
        
        try:
            await self.chat.scroll_to(key=match["control"].key, duration=300)
        except Exception:
            pass

    async def perform_search(self, e):
        query = self.search_box.value
        if not query or len(query) < 2: return await self.clear_search(e)
        
        if query == self.state["last_search_query"] and self.state["search_matches"]:
            await self.jump_to_match(self.state["active_search_index"] + 1)
            return
            
        self.state["last_search_query"] = query
        self.state["search_matches"] = []
        self.state["active_search_index"] = -1
        
        try:
            q_regex = re.escape(query)
            query_pattern = re.compile(f"({q_regex})", re.IGNORECASE)
        except Exception: return

        for control in reversed(self.chat.controls):
            if isinstance(control, ft.Row) and len(control.controls) > 1:
                bubble_container = None
                for c in control.controls:
                    if isinstance(c, ft.Container) and c.data:
                        bubble_container = c

                if bubble_container:
                    original_text = bubble_container.data
                    if query.lower() in original_text.lower():
                        count_in_msg = len(query_pattern.findall(original_text))
                        for _ in range(count_in_msg):
                            self.state["search_matches"].append({
                                "control": control,
                                "bubble": bubble_container,
                                "text": original_text
                            })
                    else:
                        if isinstance(bubble_container.content, ft.Text) and bubble_container.content.spans:
                            bubble_container.content = ui.create_message_content(
                                original_text,
                                trigger_copy_callback=lambda c: self.page.run_task(self.trigger_copy_snack, c),
                                on_tap_link=self.page.launch_url
                            )

        if self.state["search_matches"]:
            await self.jump_to_match(0)
        else:
            self.search_box.label = "0 matches"
            self.search_box.update()
            self.chat.update()

    async def clear_search(self, e):
        self.state["last_search_query"] = ""
        self.state["search_matches"] = []
        self.state["active_search_index"] = -1
        self.search_box.value = ""
        self.search_box.label = "Search"
        
        for control in self.chat.controls:
            if isinstance(control, ft.Row) and len(control.controls) > 1:
                for c in control.controls:
                    if isinstance(c, ft.Container) and c.data:
                        c.content = ui.create_message_content(
                            c.data,
                            trigger_copy_callback=lambda cb: self.page.run_task(self.trigger_copy_snack, cb),
                            on_tap_link=self.page.launch_url
                        )

        self.search_box.update()
        self.chat.update()
        self.page.update()

    async def on_key(self, e: ft.KeyboardEvent):
        if e.ctrl and e.key.lower() == "f":
            self.search_box.focus()
            self.search_box.update()
        elif e.key == "Escape":
            await self.clear_search(None)
        elif e.key == "Enter" and self.state["search_focused"]:
            if self.state["search_matches"]:
                await self.jump_to_match(self.state["active_search_index"] + 1)
            else:
                await self.perform_search(None)
