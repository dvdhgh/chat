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
14: 
15: print(f"DEBUG: Startup - Flet Version: {ft.__version__}")
16: APP_VERSION = "v3.10.5 (Layout Tweaks)"
17: # --- CONFIG ---
18: HEARTBEAT_INTERVAL = 4.0
19: HISTORY_BATCH_SIZE = 30
20: 
21: 
22: # --- MAIN APP ---
23: async def main(page: ft.Page):
24:     page_alive = True
25: 
26:     # --- APP SETTINGS & STATE ---
27:     settings = {
28:         "typing_enabled": True,
29:         "deja_vu_enabled": False  # DEFAULT: OFF to save costs
30:     }
31: 
32:     # Sync initial state to backend
33:     database.DEJA_VU_ENABLED = settings["deja_vu_enabled"]
34: 
35:     state = {
36:         "user_name": None,
37:         "last_typing_sent": 0.0,
38:         "is_temp_mode": False,
39:         "joining": False,
40:         "full_history": [],
41:         "history_cursor": 0,
42:         "is_loading_history": False,
43:         "last_search_query": ""
44:     }
45: 
46:     # Optimization: O(1) lookup for message controls
47:     message_controls = {}
48: 
49:     # --- SETUP PAGE ---
50:     page.theme_mode = ft.ThemeMode.DARK
51:     page.bgcolor = ui.PAGE_BG
52:     page.title = f"LDN Chat {APP_VERSION}"
53:     page.padding = 0
54: 
55:     # --- AUDIO PLAYER ---
56:     # --- AUDIO PLAYER (DISABLED FOR DEBUG) ---
57:     # try:
58:     #     print("DEBUG: Initializing global_audio_player...")
59:     #     global_audio_player = fta.Audio(
60:     #         src="about:blank",
61:     #         autoplay=False
62:     #     )
63:     #     page.overlay.append(global_audio_player)
64:     #     print("DEBUG: global_audio_player added to overlay.")
65:     # except Exception as e:
66:     #     print(f"CRITICAL: Failed to add Audio to overlay: {e}")
67: 
68:     file_picker = ft.FilePicker()
69: 
70:     # FilePicker and SnackBar initialization (Disabled for stability)
71:     # try:
72:     #     feedback_snack = ft.SnackBar(content=ft.Text(""), duration=1500)
73:     #     page.overlay.append(feedback_snack)
74:     # except Exception as e:
75:     #     print(f"CRITICAL: Failed to add SnackBar to overlay: {e}")
76: 
77:     # try:
78:     #     print("DEBUG: Registering FilePicker to overlay...")
79:     #     page.overlay.append(file_picker)
80:     #     print("DEBUG: FilePicker added to overlay.")
81:     # except Exception as e:
82:     #     print(f"CRITICAL: Failed to add FilePicker to overlay: {e}")
83: 
84:     # Check persistence early
85:     stored_user = None
86:     if hasattr(page, "client_storage"):
87:         stored_user = page.client_storage.get("user_name")
88: 
89:     def cache_audio_file(msg_uid, audio_ref):
90:         try:
91:             filename = f"{msg_uid}.mp4"
92:             filepath = os.path.join(database.CACHE_DIR, filename)
93:             if os.path.exists(filepath): return f"/cache/{filename}"
94: 
95:             # If audio_ref starts with gs://, download from GCS
96:             if isinstance(audio_ref, str) and audio_ref.startswith("gs://"):
97:                 bucket = database.storage_client.bucket(database.BUCKET_NAME)
98:                 blob_name = audio_ref.replace(f"gs://{database.BUCKET_NAME}/", "")
99:                 blob = bucket.blob(blob_name)
100:                 blob.download_to_filename(filepath)
101:             elif audio_ref: # Fallback for old base64 data
102:                 if isinstance(audio_ref, memoryview):
103:                     audio_ref = bytes(audio_ref)
104:                 audio_bytes = base64.b64decode(audio_ref)
105:                 with open(filepath, "wb") as f:
106:                     f.write(audio_bytes)
107:             else:
108:                 return None
109:                 
110:             return f"/cache/{filename}"
111:         except Exception as e:
112:             print(f"Cache Error: {e}")
113:             return None
114: 
115:     async def play_audio_message(msg_uid, audio_ref):
116:         print(f"DEBUG: Audio playback requested for {msg_uid} but is temporarily disabled.")
117:         # try:
118:         #     if not audio_ref: return
119:         #     feedback_snack.content.value = "Buffering from Cloud..."
120:         #     feedback_snack.open = True
121:         #     feedback_snack.update()
122:         #
123:         #     relative_url = await asyncio.to_thread(cache_audio_file, msg_uid, audio_ref)
124:         #     if not relative_url: return
125:         #
126:         #     global_audio_player.src = f"{relative_url}?t={int(time.time())}"
127:         #     global_audio_player.autoplay = True
128:         #     global_audio_player.update()
129:         #     await asyncio.sleep(0.1)
130:         #     global_audio_player.play()
131:         # except Exception as ex:
132:         #     print(f"Playback error: {ex}")
133: 
134:     # --- INIT BACKEND ---
135:     print("DEBUG: Calling database.init_db()...")
136:     database.init_db() # Idempotent call
137:     
138:     print("DEBUG: Registering session with database...")
139:     database.register_session(page.pubsub)
140:     
141:     # Consolidation of on_disconnect
142:     async def handle_disconnect(e):
143:         nonlocal page_alive
144:         print("DEBUG: Session disconnected, unregistering...")
145:         page_alive = False
146:         database.unregister_session(page.pubsub)
147:     
148:     page.on_disconnect = handle_disconnect
149: 
150:     # --- UI COMPONENTS ---
151: 
152:     # 1. COPY FEEDBACK BANNER (Toast)
153:     copy_banner = ft.Container(
154:         content=ft.Text("Copied to clipboard", color="black", size=14, weight="w500"),
155:         bgcolor="white",
156:         padding=ft.padding.only(top=12, bottom=12, left=16, right=16),
157:         border_radius=8,
158:         visible=False,
159:         bottom=20,
160:         left=20,
161:         shadow=ft.BoxShadow(
162:             spread_radius=1,
163:             blur_radius=5,
164:             color="#4d000000",
165:             offset=ft.Offset(0, 2),
166:         ),
167:         animate_opacity=300,
168:     )
169: 
170:     async def trigger_copy_snack(text_to_copy):
171:         page.set_clipboard(text_to_copy)
172:         copy_banner.visible = True
173:         copy_banner.opacity = 1
174:         copy_banner.update()
175:         await asyncio.sleep(2.0)
176:         copy_banner.visible = False
177:         copy_banner.opacity = 0
178:         copy_banner.update()
179: 
180:     # 2. HEADER ELEMENTS
181:     session_avatar = ft.CircleAvatar(radius=16, visible=False, bgcolor="#444746")
182:     session_name = ft.Text(value="", weight="bold", visible=False, color=ui.TEXT_COLOR)
183:     user_session_info = ft.Row(controls=[session_avatar, session_name])
184:     user_count_text = ft.Text(value="...", size=12, color="#8e918f", weight="bold")
185: 
186:     # 3. CHAT AREA
187:     chat = ft.ListView(
188:         expand=True,
189:         spacing=10,
190:         auto_scroll=False,
191:         reverse=True,
192:         padding=ft.padding.only(left=20, right=20, top=10, bottom=10)
193:     )
194: 
195:     chat_container = ft.Container(
196:         content=chat,
197:         expand=True,
198:         bgcolor=ui.PAGE_BG,
199:     )
200: 
201:     async def scroll_to_bottom_click(e):
202:         try:
203:             await chat.scroll_to(offset=0, duration=500, curve=ft.AnimationCurve.EASE_OUT)
204:         except Exception:
205:             pass
206: 
207:     scroll_down_button = ft.IconButton(
208:         icon=ft.Icons.ARROW_DOWNWARD,
209:         icon_color="#c4c7c5",
210:         bgcolor="#1e1f20",
211:         visible=False,
212:         on_click=scroll_to_bottom_click,
213:         tooltip="Jump to latest"
214:     )
215: 
216:     chat.on_scroll_interval = 10
217: 
218:     # --- PAGINATION LOGIC ---
219:     async def load_history_chunk():
220:         if state["is_loading_history"]: return
221: 
222:         total_available = len(state["full_history"])
223:         if state["history_cursor"] >= total_available:
224:             return
225: 
226:         state["is_loading_history"] = True
227:         start_idx = state["history_cursor"]
228:         end_idx = start_idx + HISTORY_BATCH_SIZE
229:         chunk = state["full_history"][start_idx:end_idx]
230: 
231:         print(f"DEBUG: load_history_chunk - cursor: {start_idx}, batch: {HISTORY_BATCH_SIZE}")
232:         new_controls = []
233:         for msg in chunk:
234:             try:
235:                 m = ui.create_chat_message(
236:                     msg, 
237:                     state["user_name"], 
238:                     trigger_copy_callback=lambda c: page.run_task(trigger_copy_snack, c),
239:                     on_tap_link=page.launch_url,
240:                     play_audio_callback=play_audio_message
241:                 )
242:                 if m:
243:                     message_controls[str(msg.uid)] = m
244:                     new_controls.append(m)
245:             except Exception as e:
246:                 print(f"DEBUG: Error creating message {msg.uid}: {e}")
247: 
248:         print(f"DEBUG: load_history_chunk - adding {len(new_controls)} controls to chat.")
249:         chat.controls.extend(new_controls)
250:         
251:         # DOM CAPPING: Limit to 200 messages to maintain mobile performance
252:         if len(chat.controls) > 200:
253:             chat.controls = chat.controls[:200]
254: 
255:         state["history_cursor"] = end_idx
256:         state["is_loading_history"] = False
257:         chat.update() # Explicitly update chat
258:         page.update()
259: 
260:     async def on_chat_scroll(e):
261:         try:
262:             should_show = e.pixels > 50
263:             if scroll_down_button.visible != should_show:
264:                 scroll_down_button.visible = should_show
265:                 scroll_down_button.update()
266: 
267:             if e.max_scroll_extent > 0:
268:                 if e.pixels >= (e.max_scroll_extent - 100):
269:                     await load_history_chunk()
270:         except Exception:
271:             pass
272: 
273:     chat.on_scroll = on_chat_scroll
274: 
275:     async def scroll_to_bottom(instant=False):
276:         try:
277:             duration = 0 if instant else 300
278:             curve = ft.AnimationCurve.EASE_OUT if not instant else None
279:             await chat.scroll_to(offset=0, duration=duration, curve=curve)
280:         except Exception:
281:             pass
282: 
283:     # --- INCOMING MESSAGE HANDLER ---
284:     async def handle_incoming_message(data, update_page=True):
285:         msg = database.Message(**data)
286:         uid_str = str(msg.uid)
287:         
288:         m = ui.create_chat_message(
289:             msg, 
290:             state["user_name"], 
291:             trigger_copy_callback=lambda c: page.run_task(trigger_copy_snack, c),
292:             on_tap_link=page.launch_url,
293:             play_audio_callback=play_audio_message
294:         )
295:         
296:         if uid_str in message_controls:
297:             existing_control = message_controls[uid_str]
298:             try:
299:                 idx = chat.controls.index(existing_control)
300:                 chat.controls[idx] = m
301:             except ValueError:
302:                 chat.controls.insert(0, m)
303:         else:
304:             chat.controls.insert(0, m)
305:             if msg.user_name in database.typing_status:
306:                 del database.typing_status[msg.user_name]
307: 
308:         # DOM CAPPING: Ensure the list doesn't grow indefinitely on mobile
309:         if len(chat.controls) > 200:
310:             removed = chat.controls.pop() # Remove oldest from the end
311:             # Cleanup message_controls to prevent memory leak
312:             if hasattr(removed, 'key') and removed.key in message_controls:
313:                 del message_controls[removed.key]
314:         
315:         message_controls[uid_str] = m
316: 
317:         if update_page:
318:             try:
319:                 chat.update()
320:                 # Scroll to bottom if user is at the bottom or it's their own message
321:                 if not scroll_down_button.visible or msg.user_name == state["user_name"]:
322:                     await scroll_to_bottom(instant=False)
323: 
324:                 await update_typing_ui()
325:             except Exception:
326:                 pass
327: 
328: 
329:     # --- PUBSUB LISTENER ---
330:     async def on_pubsub_message(data):
331:         if isinstance(data, dict):
332:             if data.get("message_type") == "clear_signal":
333:                 chat.controls.clear()
334:                 message_controls.clear()
335:                 state["last_msg_id"] = 0
336:                 page.update()
337:                 return
338:             if data.get("message_type") == "delete_message":
339:                 uid_to_delete = str(data.get("uid"))
340:                 if uid_to_delete in message_controls:
341:                     control = message_controls.pop(uid_to_delete)
342:                     try:
343:                         chat.controls.remove(control)
344:                         page.update()
345:                     except ValueError:
346:                         pass
347:                 return
348:             if data.get("message_type") == "typing_signal":
349:                 u_name = data.get("user_name")
350:                 if settings["typing_enabled"] and u_name != state["user_name"]:
351:                     database.typing_status[u_name] = time.time()
352:                     await update_typing_ui()
353:                 return
354:             if data.get("message_type") == "user_count":
355:                 user_count_text.value = f"{data.get('count', 0)} online"
356:                 user_count_text.update()
357:                 return
358:             if data.get("message_type") == "audio_message" and not data.get("audio_data"):
359:                 await handle_incoming_message(data)
360:                 return
361:             await handle_incoming_message(data)
362: 
363:     page.pubsub.subscribe(on_pubsub_message)
364: 
365:     # --- TYPING INDICATOR LOGIC ---
366:     typing_text = ft.Text(value="", italic=True, color="#8e918f", size=12, visible=False)
367: 
368:     async def update_typing_ui():
369:         if not settings["typing_enabled"]:
370:             if typing_text.visible:
371:                 typing_text.visible = False
372:                 typing_text.update()
373:             return
374:         now = time.time()
375:         active = [u for u, ts in database.typing_status.items()
376:                   if now - ts < database.DECAY_TIMEOUT
377:                   and u != state["user_name"]]
378:         if active:
379:             typing_text.value = f"{active[0]} is typing..." if len(active) == 1 else "Multiple people typing..."
380:             typing_text.visible = True
381:         else:
382:             typing_text.visible = False
383:         typing_text.update()
384: 
385:     async def typing_cleanup_loop():
386:         while page_alive:
387:             await asyncio.sleep(2)
388:             if typing_text.visible: await update_typing_ui()
389: 
390:     page.run_task(typing_cleanup_loop)
391: 
392:     # --- INPUT HANDLERS ---
393:     async def on_send_click(e):
394:         txt = new_message.value
395:         if not txt: return
396: 
397:         if txt.strip() == "/help":
398:             help_text = "**Commands:**\n`/lens <style>`\n`/capsule <60s> <msg>`\n`/help`"
399:             help_msg = database.Message(
400:                 user_name="SYSTEM",
401:                 text=help_text,
402:                 message_type="analysis_message",
403:                 timestamp=datetime.datetime.now().strftime("%H:%M"),
404:                 uid=str(uuid.uuid4())
405:             )
406:             chat.controls.insert(0, ui.create_chat_message(
407:                 help_msg, 
408:                 state["user_name"], 
409:                 trigger_copy_callback=lambda c: page.run_task(trigger_copy_snack, c),
410:                 on_tap_link=page.launch_url,
411:                 play_audio_callback=play_audio_message
412:             ))
413:             new_message.value = ""
414:             chat.update()
415:             new_message.update()
416:             await scroll_to_bottom(instant=False)
417:             return
418: 
419:         new_message.value = ""
420:         page.update()
421:         try:
422:             print(f"DEBUG: App sending message. text={txt[:20]}..., is_temp={state['is_temp_mode']}")
423:             # Use to_thread to prevent blocking the UI loop
424:             await asyncio.to_thread(database.insert_message, state["user_name"], txt, "chat_message", is_temp=state["is_temp_mode"])
425: 
426:         except Exception as ex:
427:             print(f"Send Error: {ex}")
428: 
429:     async def on_input_change(e):
430:         now = time.time()
431:         if state["user_name"] and (now - state["last_typing_sent"] > HEARTBEAT_INTERVAL):
432:             state["last_typing_sent"] = now
433:             database.send_typing_signal(state["user_name"])
434: 
435:     # --- FILE UPLOAD (AUDIO) ---
436:     async def on_file_picked(e):
437:         if e.files:
438:             file_obj = e.files[0]
439:             new_uid = str(uuid.uuid4())
440:             ts = datetime.datetime.now().strftime("%H:%M")
441:             safe_user = "".join(x for x in state["user_name"] if x.isalnum())
442:             filename = f"{safe_user}_{new_uid}.m4a"
443:             placeholder_data = {
444:                 "user_name": state["user_name"],
445:                 "text": "Uploading...",
446:                 "message_type": "audio_message",
447:                 "timestamp": ts,
448:                 "uid": new_uid,
449:                 "audio_data": None
450:             }
451:             await handle_incoming_message(placeholder_data)
452:             upload_url = page.get_upload_url(filename, 600)
453:             file_picker.upload([ft.FilePickerUploadFile(file_obj.name, upload_url=upload_url)])
454: 
455:             async def process_upload_background(fname, target_uid):
456:                 attempts = 0
457:                 full_path = os.path.join(database.UPLOAD_DIR, fname)
458:                 while attempts < 20:
459:                     if os.path.exists(full_path):
460:                         await asyncio.sleep(1)
461:                         try:
462:                             # Upload to GCS (Offload blocking network call)
463:                             bucket = database.storage_client.bucket(database.BUCKET_NAME)
464:                             blob = bucket.blob(fname)
465:                             await asyncio.to_thread(blob.upload_from_filename, full_path)
466:                             gcs_uri = f"gs://{database.BUCKET_NAME}/{fname}"
467:                             
468:                             await asyncio.to_thread(
469:                                 database.insert_message,
470:                                 state["user_name"],
471:                                 "Audio Message",
472:                                 "audio_message",
473:                                 is_temp=state["is_temp_mode"],
474:                                 audio_payload=gcs_uri
475:                             )
476:                             await asyncio.to_thread(os.remove, full_path)
477:                             return
478:                         except Exception as ex:
479:                             print(f"GCS Upload error: {ex}")
480:                             return
481:                     await asyncio.sleep(1)
482:                     attempts += 1
483: 
484:             page.run_task(process_upload_background, filename, new_uid)
485: 
486:     file_picker.on_result = on_file_picked
487: 
488:     # --- SEARCH OPTIMIZED ---
489:     async def perform_search(e):
490:         query = search_box.value
491:         if not query: return await clear_search(e)
492:         
493:         # Optimization: Don't re-run if query is identical
494:         if query == state["last_search_query"]:
495:             return
496:         state["last_search_query"] = query
497: 
498:         # Pre-compile search pattern once
499:         try:
500:             q_regex = re.escape(query)
501:             query_pattern = re.compile(f"({q_regex})", re.IGNORECASE)
502:         except Exception:
503:             query_pattern = None
504: 
505:         matches = 0
506:         first_key = None
507:         processed_count = 0
508:         
509:         for control in reversed(chat.controls):
510:             processed_count += 1
511:             if processed_count % 10 == 0:
512:                 await asyncio.sleep(0) # Yield for UI responsiveness
513: 
514:             if isinstance(control, ft.Row) and len(control.controls) > 1:
515:                 bubble_container = None
516:                 for c in control.controls:
517:                     if isinstance(c, ft.Container) and c.data:
518:                         bubble_container = c
519: 
520:                 if bubble_container:
521:                     original_text = bubble_container.data
522:                     is_match = query.lower() in original_text.lower()
523:                     
524:                     if is_match:
525:                         matches += 1
526:                         if not first_key: first_key = control.key
527:                         bubble_container.content = ft.Text(
528:                             spans=ui.generate_spans(original_text, page.launch_url, query_pattern=query_pattern, query_text=query),
529:                             selectable=True,
530:                             size=15,
531:                             color="#e3e3e3",
532:                             font_family="Roboto, sans-serif"
533:                         )
534:                     else:
535:                         # Selective re-rendering: Only revert if it was previously highlighted
536:                         # This avoids expensive Markdown re-builds for non-matches
537:                         if isinstance(bubble_container.content, ft.Text) and bubble_container.content.spans:
538:                             bubble_container.content = ui.create_message_content(
539:                                 original_text,
540:                                 trigger_copy_callback=lambda c: page.run_task(trigger_copy_snack, c),
541:                                 on_tap_link=page.launch_url
542:                             )
543: 
544:         chat.update()
545:         search_box.label = f"{matches} matches"
546:         search_box.update()
547:         try:
548:             if first_key: await chat.scroll_to(offset=0, duration=500)
549:         except Exception as ex:
550:             print(f"Search scroll failed: {ex}")
551: 
552:     async def clear_search(e):
553:         search_box.value = ""
554:         search_box.label = "Search"
555:         state["history_cursor"] = 0
556:         chat.controls.clear()
557:         await load_history_chunk()
558:         page.update()
559: 
560:     search_box = ft.TextField(
561:         label="Search",
562:         width=250,
563:         height=40,
564:         content_padding=ft.padding.only(left=15, right=10, top=5),
565:         border_radius=20,
566:         bgcolor="#1e1f20",
567:         border_width=0,
568:         text_style=ft.TextStyle(color="white"),
569:         label_style=ft.TextStyle(color="#8e918f"),
570:         on_submit=perform_search,
571:         suffix=ft.Container(
572:             content=ft.Icon(ft.Icons.CLOSE, size=16, color="#8e918f"),
573:             on_click=clear_search,
574:             padding=5,
575:             ink=True,
576:             border_radius=20
577:         )
578:     )
579: 
580:     # --- SETTINGS / ADMIN ---
581:     async def clear_database_click(e):
582:         if await asyncio.to_thread(database.clear_global_database):
583:             page.snack_bar = ft.SnackBar(content=ft.Text("GLOBAL DATABASE CLEARED"))
584:             page.snack_bar.open = True
585:             page.update()
586: 
587:     def update_deja_vu(e):
588:         settings["deja_vu_enabled"] = deja_vu_switch.value
589:         database.DEJA_VU_ENABLED = settings["deja_vu_enabled"]
590:         print(f"DEBUG: Deja Vu Enabled = {database.DEJA_VU_ENABLED}")
591: 
592:     typing_switch = ft.Switch(
593:         label="Typing Indicator",
594:         value=True,
595:         on_change=lambda e: setattr(settings, "typing_enabled", typing_switch.value)
596:     )
597: 
598:     deja_vu_switch = ft.Switch(
599:         label="Enable Déjà Vu (AI)",
600:         value=False,
601:         on_change=update_deja_vu
602:     )
603: 
604:     clear_button = ft.FilledButton(
605:         "Clear Global Database",
606:         style=ft.ButtonStyle(bgcolor="#B71C1C", color="white"),
607:         on_click=clear_database_click
608:     )
609: 
610:     uptime_text = ft.Text(size=12, color="#8e918f")
611: 
612:     settings_sheet = ft.BottomSheet(
613:         ft.Container(
614:             ft.Column([
615:                 ft.Text("Settings", weight="bold", size=18, color="white"),
616:                 ft.Divider(color="#444746"),
617:                 typing_switch,
618:                 deja_vu_switch,
619:                 ft.Divider(color="#444746"),
620:                 ft.Text("Administrative", weight="bold", color="#8e918f"),
621:                 clear_button,
622:                 uptime_text
623:             ], tight=True, spacing=15),
624:             padding=25,
625:             bgcolor="#1e1f20",
626:             border_radius=ft.border_radius.only(top_left=25, top_right=25)
627:         )
628:     )
629: 
630:     def open_settings(e):
631:         page.overlay.append(settings_sheet)
632:         settings_sheet.open = True
633:         settings_sheet.update()
634: 
635:     # --- USER AUTH / JOIN ---
636:     login_dialog = ft.AlertDialog(
637:         modal=True,
638:         title=ft.Text("Welcome to LDN Chat"),
639:         content=ft.Column([
640:             ft.Text("Choose a name to join the session."),
641:             ft.TextField(label="Your Name", on_submit=lambda e: join_chat_click(e))
642:         ], tight=True),
643:         actions=[
644:             ft.TextButton("JOIN CHAT", on_click=lambda e: join_chat_click(e))
645:         ],
646:         actions_alignment=ft.MainAxisAlignment.END,
647:     )
648: 
649:     async def join_chat_click(e):
650:         name_field = login_dialog.content.controls[1]
651:         if not name_field.value:
17:             name_field.error_text = "Name is required"
18:             name_field.update()
19:             return
20: 
21:         state["user_name"] = name_field.value
22:         if hasattr(page, "client_storage"):
23:             page.client_storage.set("user_name", state["user_name"])
24: 
25:         login_dialog.open = False
26:         page.update()
27: 
28:         # Update session UI
29:         session_avatar.content = ft.Text(state["user_name"][:1].upper(), color="white")
30:         session_avatar.bgcolor = ui.BUBBLE_BG
31:         session_avatar.visible = True
32:         session_name.value = state["user_name"]
33:         session_name.visible = True
34:         
35:         # Trigger join message
36:         await asyncio.to_thread(database.insert_message, "SYSTEM", f"{state['user_name']} joined", "login_message")
37:         
38:         # Initial History Load (Backgrounded for mobile)
39:         async def load_initial_history():
40:             state["full_history"] = await asyncio.to_thread(database.get_recent_messages)
41:             await load_history_chunk()
42:             await scroll_to_bottom(instant=True)
43:             
44:         page.run_task(load_initial_history)
44: 
45:     if stored_user:
46:         state["user_name"] = stored_user
47:         session_avatar.content = ft.Text(state["user_name"][:1].upper(), color="white")
48:         session_avatar.bgcolor = ui.BUBBLE_BG
49:         session_avatar.visible = True
50:         session_name.value = state["user_name"]
51:         session_name.visible = True
52:         
53:         async def load_initial_history_stored():
54:             state["full_history"] = await asyncio.to_thread(database.get_recent_messages)
55:             await load_history_chunk()
56:             await scroll_to_bottom(instant=True)
57:         page.run_task(load_initial_history_stored)
58:     else:
59:         page.dialog = login_dialog
60:         login_dialog.open = True
61:         page.update()
62: 
63:     # --- HEADER (RESPONSIVE) ---
64:     search_expanded = False
65:     
66:     async def toggle_search_mobile(e):
67:         nonlocal search_expanded
68:         search_expanded = not search_expanded
69:         
70:         # Update visibility
71:         search_box.visible = search_expanded
72:         settings_btn.visible = not search_expanded
73:         logout_btn.visible = not search_expanded
74:         user_session_info.visible = not search_expanded
75:         
76:         # Change icon
77:         search_btn_mobile.icon = ft.Icons.CLOSE if search_expanded else ft.Icons.SEARCH
78:         
79:         header.update()
80:         if search_expanded:
81:             search_box.focus()
82: 
83:     search_btn_mobile = ft.IconButton(
84:         icon=ft.Icons.SEARCH,
85:         icon_color="#8e918f",
86:         visible=False,
87:         on_click=toggle_search_mobile
88:     )
89: 
90:     settings_btn = ft.IconButton(
91:         icon=ft.Icons.SETTINGS,
92:         icon_color="#8e918f",
93:         tooltip="Settings",
94:         on_click=open_settings
95:     )
96: 
97:     async def logout_click(e):
98:         if hasattr(page, "client_storage"):
99:             page.client_storage.remove("user_name")
100:         page.window_reload()
101: 
102:     logout_btn = ft.IconButton(
103:         icon=ft.Icons.LOGOUT,
104:         icon_color="#8e918f",
105:         tooltip="Logout",
106:         on_click=logout_click
107:     )
108: 
109:     header = ft.Container(
110:         content=ft.Row([
111:             ft.Row([
112:                 user_session_info,
113:                 ft.Container(content=user_count_text, padding=ft.padding.only(left=10))
114:             ], expand=True),
115:             ft.Row([
116:                 search_box,
117:                 search_btn_mobile,
118:                 settings_btn,
119:                 logout_btn
120:             ], alignment=ft.MainAxisAlignment.END)
121:         ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
122:         padding=ft.padding.only(left=20, right=10, top=10, bottom=10),
123:         bgcolor="#1e1f20",
124:         border=ft.border.only(bottom=ft.BorderSide(1, "#303134"))
125:     )
126: 
127:     # --- INPUT BAR ---
128:     new_message = ft.TextField(
129:         hint_text="Type a message...",
130:         expand=True,
131:         border_radius=25,
132:         bgcolor="#1e1f20",
133:         border_width=0,
134:         content_padding=ft.padding.only(left=20, right=20, top=12, bottom=12),
135:         on_submit=on_send_click,
136:         on_change=on_input_change,
137:         text_style=ft.TextStyle(color=ui.TEXT_COLOR)
138:     )
139: 
140:     input_bar = ft.Container(
141:         content=ft.Column([
142:             ft.Row([
143:                 ft.IconButton(
144:                     icon=ft.Icons.TIMER_OUTLINED,
145:                     icon_color="#FAFAFA" if state["is_temp_mode"] else "#8e918f",
146:                     on_click=lambda e: toggle_temp_mode(e),
147:                     tooltip="Toggle Temp Mode (60s)"
148:                 ),
149:                 new_message,
150:                 ft.IconButton(
151:                     icon=ft.Icons.SEND_ROUNDED,
152:                     icon_color=ft.Colors.BLUE_400,
153:                     on_click=on_send_click
154:                 ),
155:             ]),
156:             ft.Container(content=typing_text, padding=ft.padding.only(left=60, bottom=5))
157:         ], tight=True),
158:         padding=ft.padding.only(left=10, right=10, bottom=20, top=10),
159:         bgcolor=ui.PAGE_BG
160:     )
161: 
162:     async def toggle_temp_mode(e):
163:         state["is_temp_mode"] = not state["is_temp_mode"]
164:         e.control.icon_color = "#FAFAFA" if state["is_temp_mode"] else "#8e918f"
165:         e.control.update()
166: 
167:     # --- RESPONSIVITY HELPER ---
168:     def on_page_resize(e):
169:         is_mobile = page.width < 600
170:         search_box.visible = not is_mobile
171:         search_btn_mobile.visible = is_mobile
172:         page.update()
173: 
174:     page.on_resize = on_page_resize
175:     on_page_resize(None) # Initial check
176: 
177:     # --- FINAL LAYOUT ---
178:     # Add floating action button for "Scroll to bottom"
179:     page.add(
180:         ft.Stack([
181:             ft.Column([header, chat_container, input_bar], expand=True, spacing=0),
182:             ft.Container(
183:                 content=scroll_down_button,
184:                 bottom=100,
185:                 right=20,
186:             ),
187:             copy_banner # Global toast
188:         ], expand=True)
189:     )
190: 
191: # Run
192: ft.app(target=main, view=ft.AppView.WEB_BROWSER, port=int(os.getenv("PORT", 8080)), assets_dir="assets")
