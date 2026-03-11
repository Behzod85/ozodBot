from typing import Optional
import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from models import User, Template, Order, OrderStep, TemplateStep
from models import Process

logger = logging.getLogger(__name__)

PAGE_SIZE = 6

# track messages sent for paginated views so we can delete item messages when pages change
# key: (chat_id, view) -> { 'header_id': int, 'item_ids': [int] }
_sent_messages = {}


async def _send_message_and_get_id(bot, chat_id: int, text: str, reply_markup: Optional[InlineKeyboardMarkup] = None):
    try:
        resp = await bot.send_message(chat_id=chat_id, text=text, reply_markup=reply_markup)
        return getattr(resp, 'message_id', None)
    except Exception as e:
        logger.exception("Failed to send message chat=%s len=%s error=%s", chat_id, len(text) if text is not None else 0, e)
        try:
            # fallback: safe send without markup (splits long messages)
            await _send_or_edit(bot, chat_id, text, reply_markup=None)
        except Exception:
            logger.exception("Fallback _send_or_edit failed for chat=%s", chat_id)
        return None


async def _send_or_edit(bot, chat_id: int, text: str, reply_markup: Optional[InlineKeyboardMarkup] = None, edit_query=None):
    max_len = 4000
    try:
        if edit_query is not None:
            # For edits, if text is too long, edit to the first chunk and send remaining as follow-up messages
            if len(text) <= max_len:
                await edit_query.edit_message_text(text, reply_markup=reply_markup)
            else:
                first = text[:max_len]
                await edit_query.edit_message_text(first + "\n\n...[truncated]", reply_markup=reply_markup)
                rest = text[len(first):]
                while rest:
                    chunk = rest[:max_len]
                    await bot.send_message(chat_id=chat_id, text=chunk)
                    rest = rest[len(chunk):]
        else:
            # When sending a new message, split into chunks that fit Telegram limits
            if len(text) <= max_len:
                await bot.send_message(chat_id=chat_id, text=text, reply_markup=reply_markup)
            else:
                current = text
                first = current[:max_len]
                await bot.send_message(chat_id=chat_id, text=first, reply_markup=reply_markup)
                current = current[len(first):]
                while current:
                    chunk = current[:max_len]
                    await bot.send_message(chat_id=chat_id, text=chunk)
                    current = current[len(chunk):]
    except Exception as e:
        # Log detailed failure info so we can diagnose 400s (message too long, bad markup, etc.)
        try:
            rb_repr = repr(reply_markup) if reply_markup is not None else "<no-reply-markup>"
        except Exception:
            rb_repr = "<reply-markup-repr-failed>"
        logger.exception("Failed to send/edit message chat=%s len=%s reply_markup=%s error=%s", chat_id, len(text) if text is not None else 0, rb_repr, e)
        # Best-effort fallback: try sending a truncated plain message without markup
        try:
            if text is None:
                return
            if len(text) > max_len:
                await bot.send_message(chat_id=chat_id, text=text[:max_len])
            else:
                await bot.send_message(chat_id=chat_id, text=text)
        except Exception:
            logger.exception("Fallback send failed for chat=%s", chat_id)


def _build_nav(view: str, page: int, total_pages: int, extra: str = None):
    kb = []
    nav = []
    def cb(p):
        if extra is None:
            return f"page:{view}:{p}"
        return f"page:{view}:{extra}:{p}"

    if page > 1:
        nav.append(InlineKeyboardButton("◀️ Orqaga", callback_data=cb(page-1)))
    nav.append(InlineKeyboardButton(f"{page}/{total_pages}", callback_data=cb(page)))
    if page < total_pages:
        nav.append(InlineKeyboardButton("Keyingi ▶️", callback_data=cb(page+1)))
    if nav:
        kb.append(nav)
    return kb


async def pending_users_page(session, chat_id, bot, page: int = 1, edit_query=None):
    logger.info("pagination.pending_users_page called chat=%s page=%s", chat_id, page)
    q = session.query(User).filter(User.approved == False)
    total = q.count()
    if total == 0:
        await _send_or_edit(bot, chat_id, "Kutilayotgan arizalar yo'q.", edit_query=edit_query)
        return
    total_pages = (total + PAGE_SIZE - 1) // PAGE_SIZE
    page = max(1, min(page, total_pages))
    items = q.order_by(User.id).limit(PAGE_SIZE).offset((page - 1) * PAGE_SIZE).all()

    header_text = f"Kutilayotgan arizalar — sahifa {page}/{total_pages}"
    nav_kb = _build_nav("pending_users", page, total_pages)

    key = (chat_id, "pending_users")
    prev = _sent_messages.get(key)
    if prev:
        for mid in prev.get("item_ids", []):
            try:
                await bot.delete_message(chat_id=chat_id, message_id=mid)
            except Exception:
                pass

    header_id = None
    try:
        if edit_query is not None:
            await edit_query.edit_message_text(header_text, reply_markup=InlineKeyboardMarkup(nav_kb))
            header_id = edit_query.message.message_id
        else:
            resp = await bot.send_message(chat_id=chat_id, text=header_text, reply_markup=InlineKeyboardMarkup(nav_kb))
            header_id = getattr(resp, 'message_id', None)
    except Exception:
        try:
            resp = await bot.send_message(chat_id=chat_id, text=header_text, reply_markup=InlineKeyboardMarkup(nav_kb))
            header_id = getattr(resp, 'message_id', None)
        except Exception:
            header_id = None

    item_msg_ids = []
    for u in items:
        text = f"tg={u.telegram_id} id={u.id}\nname={u.name}\nrole={u.role}"
        kb = [[
            InlineKeyboardButton("Ishchi", callback_data=f"set_role:{u.telegram_id}:worker"),
            InlineKeyboardButton("Direktor", callback_data=f"set_role:{u.telegram_id}:director"),
            InlineKeyboardButton("Mijoz", callback_data=f"set_role:{u.telegram_id}:client"),
        ]]
        mid = await _send_message_and_get_id(bot, chat_id, text, InlineKeyboardMarkup(kb))
        if mid is not None:
            item_msg_ids.append(mid)

    _sent_messages[key] = {"header_id": header_id, "item_ids": item_msg_ids}


async def workers_page(session, chat_id, bot, page: int = 1, edit_query=None):
    logger.info("pagination.workers_page called chat=%s page=%s", chat_id, page)
    q = session.query(User).filter(User.role == "worker", User.approved == True)
    total = q.count()
    if total == 0:
        await _send_or_edit(bot, chat_id, "Hozircha tasdiqlangan ishchilar yo'q.", edit_query=edit_query)
        return
    total_pages = (total + PAGE_SIZE - 1) // PAGE_SIZE
    page = max(1, min(page, total_pages))
    items = q.order_by(User.id).limit(PAGE_SIZE).offset((page - 1) * PAGE_SIZE).all()

    header_text = f"Ishchilar — sahifa {page}/{total_pages}"
    nav_kb = _build_nav("list_workers", page, total_pages)

    key = (chat_id, "list_workers")
    prev = _sent_messages.get(key)
    if prev:
        for mid in prev.get("item_ids", []):
            try:
                await bot.delete_message(chat_id=chat_id, message_id=mid)
            except Exception:
                pass

    header_id = None
    try:
        if edit_query is not None:
            await edit_query.edit_message_text(header_text, reply_markup=InlineKeyboardMarkup(nav_kb))
            header_id = edit_query.message.message_id
        else:
            resp = await bot.send_message(chat_id=chat_id, text=header_text, reply_markup=InlineKeyboardMarkup(nav_kb))
            header_id = getattr(resp, 'message_id', None)
    except Exception:
        try:
            resp = await bot.send_message(chat_id=chat_id, text=header_text, reply_markup=InlineKeyboardMarkup(nav_kb))
            header_id = getattr(resp, 'message_id', None)
        except Exception:
            header_id = None

    item_msg_ids = []
    for w in items:
        text = f"tg={w.telegram_id} id={w.id}\nname={w.name}\nrole={w.role}"
        kb = [[
            InlineKeyboardButton("O'chirish", callback_data=f"worker_delete:{w.telegram_id}"),
            InlineKeyboardButton("Qayta nomlash", callback_data=f"worker_rename:{w.telegram_id}"),
        ]]
        mid = await _send_message_and_get_id(bot, chat_id, text, InlineKeyboardMarkup(kb))
        if mid is not None:
            item_msg_ids.append(mid)

    _sent_messages[key] = {"header_id": header_id, "item_ids": item_msg_ids}


async def clients_page(session, chat_id, bot, page: int = 1, edit_query=None):
    logger.info("pagination.clients_page called chat=%s page=%s", chat_id, page)
    q = session.query(User).filter(User.role == "client", User.approved == True)
    total = q.count()
    if total == 0:
        await _send_or_edit(bot, chat_id, "Hozircha tasdiqlangan mijozlar yo'q.", edit_query=edit_query)
        return
    total_pages = (total + PAGE_SIZE - 1) // PAGE_SIZE
    page = max(1, min(page, total_pages))
    items = q.order_by(User.id).limit(PAGE_SIZE).offset((page - 1) * PAGE_SIZE).all()

    header_text = f"Mijozlar — sahifa {page}/{total_pages}"
    nav_kb = _build_nav("list_clients", page, total_pages)

    key = (chat_id, "list_clients")
    prev = _sent_messages.get(key)
    if prev:
        for mid in prev.get("item_ids", []):
            try:
                await bot.delete_message(chat_id=chat_id, message_id=mid)
            except Exception:
                pass

    header_id = None
    try:
        if edit_query is not None:
            await edit_query.edit_message_text(header_text, reply_markup=InlineKeyboardMarkup(nav_kb))
            header_id = edit_query.message.message_id
        else:
            resp = await bot.send_message(chat_id=chat_id, text=header_text, reply_markup=InlineKeyboardMarkup(nav_kb))
            header_id = getattr(resp, 'message_id', None)
    except Exception:
        try:
            resp = await bot.send_message(chat_id=chat_id, text=header_text, reply_markup=InlineKeyboardMarkup(nav_kb))
            header_id = getattr(resp, 'message_id', None)
        except Exception:
            header_id = None

    item_msg_ids = []
    for c in items:
        text = f"tg={c.telegram_id} id={c.id}\nname={c.name}\nrole={c.role}"
        kb = [[
            InlineKeyboardButton("O'chirish", callback_data=f"client_delete:{c.telegram_id}"),
            InlineKeyboardButton("Qayta nomlash", callback_data=f"client_rename:{c.telegram_id}"),
        ]]
        mid = await _send_message_and_get_id(bot, chat_id, text, InlineKeyboardMarkup(kb))
        if mid is not None:
            item_msg_ids.append(mid)

    _sent_messages[key] = {"header_id": header_id, "item_ids": item_msg_ids}


async def templates_page(session, chat_id, bot, page: int = 1, is_director: bool = False, edit_query=None):
    logger.info("pagination.templates_page called chat=%s page=%s is_director=%s", chat_id, page, is_director)
    q = session.query(Template)
    total = q.count()
    if total == 0:
        await _send_or_edit(bot, chat_id, "Hozircha shablonlar mavjud emas.", edit_query=edit_query)
        return
    total_pages = (total + PAGE_SIZE - 1) // PAGE_SIZE
    page = max(1, min(page, total_pages))
    items = q.order_by(Template.id).limit(PAGE_SIZE).offset((page - 1) * PAGE_SIZE).all()

    header_text = f"Shablonlar — sahifa {page}/{total_pages}"
    nav_kb = _build_nav("list_templates", page, total_pages)

    key = (chat_id, "list_templates")
    prev = _sent_messages.get(key)
    if prev:
        for mid in prev.get("item_ids", []):
            try:
                await bot.delete_message(chat_id=chat_id, message_id=mid)
            except Exception:
                pass

    header_id = None
    try:
        if edit_query is not None:
            await edit_query.edit_message_text(header_text, reply_markup=InlineKeyboardMarkup(nav_kb))
            header_id = edit_query.message.message_id
        else:
            resp = await bot.send_message(chat_id=chat_id, text=header_text, reply_markup=InlineKeyboardMarkup(nav_kb))
            header_id = getattr(resp, 'message_id', None)
    except Exception:
        try:
            resp = await bot.send_message(chat_id=chat_id, text=header_text, reply_markup=InlineKeyboardMarkup(nav_kb))
            header_id = getattr(resp, 'message_id', None)
        except Exception:
            header_id = None

    item_msg_ids = []
    for t in items:
        parts = [f"[{t.id}] {t.name}"]
        for s in t.steps:
            instr = getattr(s, 'instruction_text', '') or ''
            noti = getattr(s, 'notification_text', '') or ''
            if getattr(s, 'process', None):
                instr = getattr(s.process, 'instruction_text', instr) or ''
                noti = getattr(s.process, 'notification_text', noti) or ''
            parts.append(f"({s.position}) nomi={instr[:60]}\nnotify={noti[:60]}...")
        text = "\n".join(parts)
        kb = None
        if is_director:
            kb = [[
                InlineKeyboardButton("O'chirish", callback_data=f"template_delete:{t.id}"),
                InlineKeyboardButton("Qayta nomlash", callback_data=f"template_rename:{t.id}"),
            ]]
        mid = await _send_message_and_get_id(bot, chat_id, text, InlineKeyboardMarkup(kb) if kb else None)
        if mid is not None:
            item_msg_ids.append(mid)

    _sent_messages[key] = {"header_id": header_id, "item_ids": item_msg_ids}


async def processes_page(session, chat_id, bot, page: int = 1, edit_query=None):
    q = session.query(Process)
    total = q.count()
    if total == 0:
        await _send_or_edit(bot, chat_id, "Hozircha qadamlar mavjud emas.", edit_query=edit_query)
        return
    total_pages = (total + PAGE_SIZE - 1) // PAGE_SIZE
    page = max(1, min(page, total_pages))
    items = q.order_by(Process.id).limit(PAGE_SIZE).offset((page - 1) * PAGE_SIZE).all()

    header_text = f"Qadamlar — sahifa {page}/{total_pages}"
    nav_kb = _build_nav("list_processes", page, total_pages)

    key = (chat_id, "list_processes")
    prev = _sent_messages.get(key)
    if prev:
        for mid in prev.get("item_ids", []):
            try:
                await bot.delete_message(chat_id=chat_id, message_id=mid)
            except Exception:
                pass

    header_id = None
    try:
        if edit_query is not None:
            await edit_query.edit_message_text(header_text, reply_markup=InlineKeyboardMarkup(nav_kb))
            header_id = edit_query.message.message_id
        else:
            resp = await bot.send_message(chat_id=chat_id, text=header_text, reply_markup=InlineKeyboardMarkup(nav_kb))
            header_id = getattr(resp, 'message_id', None)
    except Exception:
        try:
            resp = await bot.send_message(chat_id=chat_id, text=header_text, reply_markup=InlineKeyboardMarkup(nav_kb))
            header_id = getattr(resp, 'message_id', None)
        except Exception:
            header_id = None

    item_msg_ids = []
    for p in items:
        instr = p.instruction_text or ''
        noti = p.notification_text or ''
        text = f"id={p.id}\n{instr}\nnotify={noti}"
        kb = [[
            InlineKeyboardButton("O'chirish", callback_data=f"process_delete:{p.id}"),
            InlineKeyboardButton("Qayta nomlash", callback_data=f"process_rename:{p.id}"),
        ]] 
        mid = await _send_message_and_get_id(bot, chat_id, text, InlineKeyboardMarkup(kb))
        if mid is not None:
            item_msg_ids.append(mid)

    _sent_messages[key] = {"header_id": header_id, "item_ids": item_msg_ids}


async def select_processes_for_template(session, chat_id, bot, template_id: int, page: int = 1, edit_query=None, context=None):
    q = session.query(Process)
    total = q.count()
    if total == 0:
        await _send_or_edit(bot, chat_id, "Hozircha qadamlar mavjud emas.", edit_query=edit_query)
        return
    total_pages = (total + PAGE_SIZE - 1) // PAGE_SIZE
    page = max(1, min(page, total_pages))
    items = q.order_by(Process.id).limit(PAGE_SIZE).offset((page - 1) * PAGE_SIZE).all()

    header_text = f"Qadamni tanlang — sahifa {page}/{total_pages}"
    nav_kb = _build_nav("select_processes_for_template", page, total_pages, extra=str(template_id))
    # include finish button on the header
    header_kb = nav_kb.copy()
    header_kb.append([InlineKeyboardButton("Yaratish", callback_data=f"create_template:finish:{template_id}")])

    # determine currently selected processes from user context (if provided)
    selected = []
    if context is not None:
        ct = context.user_data.get("create_template")
        if ct and ct.get("template_id") == template_id:
            selected = ct.get("selected", [])

    key = (chat_id, f"select_processes_for_template:{template_id}")
    prev = _sent_messages.get(key)
    # Determine whether we should delete previous per-item messages.
    # New format stores an "item_map" and a "page". For legacy entries with
    # "item_ids" we fall back to deleting all.
    prev_item_map = None
    prev_page = None
    if prev:
        prev_item_map = prev.get("item_map")
        prev_page = prev.get("page")
        if prev_item_map is None:
            # legacy: delete all previous item_ids
            for mid in prev.get("item_ids", []):
                try:
                    await bot.delete_message(chat_id=chat_id, message_id=mid)
                except Exception:
                    pass
        else:
            # only delete previous items if page changed
            if prev_page is None or prev_page != page:
                for mid in prev_item_map.values():
                    try:
                        await bot.delete_message(chat_id=chat_id, message_id=mid)
                    except Exception:
                        pass

    header_id = None
    try:
        prev_header_id = prev.get("header_id") if prev else None
        if edit_query is not None:
            # If the callback came from the header message (navigation), edit it in-place.
            if prev_header_id and edit_query.message and edit_query.message.message_id == prev_header_id:
                await edit_query.edit_message_text(header_text, reply_markup=InlineKeyboardMarkup(header_kb))
                header_id = edit_query.message.message_id
            else:
                # callback did not originate from header; edit the stored header if possible,
                # otherwise send a new header message.
                if prev_header_id:
                    try:
                        await bot.edit_message_text(text=header_text, chat_id=chat_id, message_id=prev_header_id, reply_markup=InlineKeyboardMarkup(header_kb))
                        header_id = prev_header_id
                    except Exception:
                        resp = await bot.send_message(chat_id=chat_id, text=header_text, reply_markup=InlineKeyboardMarkup(header_kb))
                        header_id = getattr(resp, 'message_id', None)
                else:
                    resp = await bot.send_message(chat_id=chat_id, text=header_text, reply_markup=InlineKeyboardMarkup(header_kb))
                    header_id = getattr(resp, 'message_id', None)
        else:
            resp = await bot.send_message(chat_id=chat_id, text=header_text, reply_markup=InlineKeyboardMarkup(header_kb))
            header_id = getattr(resp, 'message_id', None)
    except Exception:
        try:
            resp = await bot.send_message(chat_id=chat_id, text=header_text, reply_markup=InlineKeyboardMarkup(header_kb))
            header_id = getattr(resp, 'message_id', None)
        except Exception:
            header_id = None

    # Build or update per-item messages. If we have a previous item_map and the
    # page is unchanged, update each item's text/reply_markup in-place. This
    # prevents deleting all messages when toggling a single selection.
    item_msg_map = {}
    for p in items:
        sel_mark = " ✅" if p.id in selected else ""
        instr = p.instruction_text or ''
        noti = p.notification_text or ''
        text = f"[{p.id}] {instr[:80]}{sel_mark}\nnotify={noti[:60]}"
        btn_text = "✅ Tanlangan" if p.id in selected else "Tanlash"
        # include current page in callback so the handler can refresh the same page
        kb = [[InlineKeyboardButton(btn_text, callback_data=f"select_process:{template_id}:{p.id}:{page}")]]

        updated = False
        if prev_item_map and prev_page == page and p.id in prev_item_map:
            old_mid = prev_item_map.get(p.id)
            try:
                await bot.edit_message_text(text=text, chat_id=chat_id, message_id=old_mid, reply_markup=InlineKeyboardMarkup(kb))
                item_msg_map[p.id] = old_mid
                updated = True
            except Exception as e:
                err = str(e)
                logger.debug("edit_message_text failed for select_processes_for_template chat=%s tpl=%s pid=%s mid=%s error=%s", chat_id, template_id, p.id, old_mid, err)
                # If Telegram reports the message is not modified, treat as success and keep the old message id
                if "not modified" in err.lower() or "message is not modified" in err.lower():
                    item_msg_map[p.id] = old_mid
                    updated = True
                else:
                    # try to remove the stale message before re-sending to avoid duplicates
                    try:
                        await bot.delete_message(chat_id=chat_id, message_id=old_mid)
                    except Exception:
                        pass

        if not updated:
            mid = await _send_message_and_get_id(bot, chat_id, text, InlineKeyboardMarkup(kb))
            if mid is not None:
                item_msg_map[p.id] = mid

    _sent_messages[key] = {"header_id": header_id, "item_map": item_msg_map, "page": page}


async def orders_created_page(session, chat_id, bot, page: int = 1, edit_query=None):
    logger.info("pagination.orders_created_page called chat=%s page=%s", chat_id, page)
    q = session.query(Order).filter(Order.status == "created")
    total = q.count()
    if total == 0:
        await _send_or_edit(bot, chat_id, "Hozircha ishga tushirilmagan buyurtmalar yo'q.", edit_query=edit_query)
        return
    total_pages = (total + PAGE_SIZE - 1) // PAGE_SIZE
    page = max(1, min(page, total_pages))
    items = q.order_by(Order.id).limit(PAGE_SIZE).offset((page - 1) * PAGE_SIZE).all()

    header_text = f"Buyurtmalar (yaratilgan) — sahifa {page}/{total_pages}"
    nav_kb = _build_nav("orders_created", page, total_pages)

    key = (chat_id, "orders_created")
    prev = _sent_messages.get(key)
    if prev:
        for mid in prev.get("item_ids", []):
            try:
                await bot.delete_message(chat_id=chat_id, message_id=mid)
            except Exception:
                pass

    header_id = None
    try:
        if edit_query is not None:
            await edit_query.edit_message_text(header_text, reply_markup=InlineKeyboardMarkup(nav_kb))
            header_id = edit_query.message.message_id
        else:
            resp = await bot.send_message(chat_id=chat_id, text=header_text, reply_markup=InlineKeyboardMarkup(nav_kb))
            header_id = getattr(resp, 'message_id', None)
    except Exception:
        try:
            resp = await bot.send_message(chat_id=chat_id, text=header_text, reply_markup=InlineKeyboardMarkup(nav_kb))
            header_id = getattr(resp, 'message_id', None)
        except Exception:
            header_id = None

    item_msg_ids = []
    for o in items:
        client_name = o.client.name if o.client else str(o.client_id)
        order_name = getattr(o, 'name', '') or ''
        order_description = getattr(o, 'description', '') or ''
        # collect instruction text from template/order steps
        try:
            instrs = [s.instruction_text for s in o.steps if getattr(s, 'instruction_text', None)]
            instruction_text = "\n".join(instrs)
        except Exception:
            instruction_text = ""
        text = f"Mijoz: {client_name}\nNomi: {order_name}\nTavsifi: {order_description}\n{instruction_text}"
        kb = [[InlineKeyboardButton("Boshlash", callback_data=f"start_order:{o.id}")]]
        mid = await _send_message_and_get_id(bot, chat_id, text, InlineKeyboardMarkup(kb))
        if mid is not None:
            item_msg_ids.append(mid)

    _sent_messages[key] = {"header_id": header_id, "item_ids": item_msg_ids}


async def orders_page(session, chat_id, bot, page: int = 1, edit_query=None):
    logger.info("pagination.orders_page called chat=%s page=%s", chat_id, page)
    q = session.query(Order).order_by(Order.id)
    total = q.count()
    if total == 0:
        await _send_or_edit(bot, chat_id, "Hozircha buyurtmalar mavjud emas.", edit_query=edit_query)
        return
    total_pages = (total + PAGE_SIZE - 1) // PAGE_SIZE
    page = max(1, min(page, total_pages))
    items = q.limit(PAGE_SIZE).offset((page - 1) * PAGE_SIZE).all()

    header_text = f"Buyurtmalar — sahifa {page}/{total_pages}"
    nav_kb = _build_nav("orders", page, total_pages)

    key = (chat_id, "orders")
    prev = _sent_messages.get(key)
    if prev:
        for mid in prev.get("item_ids", []):
            try:
                await bot.delete_message(chat_id=chat_id, message_id=mid)
            except Exception:
                pass

    header_id = None
    try:
        if edit_query is not None:
            await edit_query.edit_message_text(header_text, reply_markup=InlineKeyboardMarkup(nav_kb))
            header_id = edit_query.message.message_id
        else:
            resp = await bot.send_message(chat_id=chat_id, text=header_text, reply_markup=InlineKeyboardMarkup(nav_kb))
            header_id = getattr(resp, 'message_id', None)
    except Exception:
        try:
            resp = await bot.send_message(chat_id=chat_id, text=header_text, reply_markup=InlineKeyboardMarkup(nav_kb))
            header_id = getattr(resp, 'message_id', None)
        except Exception:
            header_id = None

    item_msg_ids = []
    for o in items:
        client_name = o.client.name if o.client else str(o.client_id)
        order_name = getattr(o, 'name', '') or ''
        order_description = getattr(o, 'description', '') or ''
        try:
            instrs = [s.instruction_text for s in o.steps if getattr(s, 'instruction_text', None)]
            instruction_text = "\n".join(instrs)
        except Exception:
            instruction_text = ""
        text = f"#{o.id} Mijoz: {client_name}\nNomi: {order_name}\nTavsifi: {order_description}\n{instruction_text}"
        kb = [[InlineKeyboardButton("Buyurtma statusi", callback_data=f"order_status:{o.id}" )]]
        mid = await _send_message_and_get_id(bot, chat_id, text, InlineKeyboardMarkup(kb))
        if mid is not None:
            item_msg_ids.append(mid)

    _sent_messages[key] = {"header_id": header_id, "item_ids": item_msg_ids}


async def my_orders_page(session, chat_id, bot, client_id: int, page: int = 1, edit_query=None):
    logger.info("pagination.my_orders_page called chat=%s client_id=%s page=%s", chat_id, client_id, page)
    q = session.query(Order).filter(Order.client_id == client_id).order_by(Order.created_at.desc())
    total = q.count()
    if total == 0:
        await _send_or_edit(bot, chat_id, "Sizda buyurtmalar yo'q.", edit_query=edit_query)
        return
    total_pages = (total + PAGE_SIZE - 1) // PAGE_SIZE
    page = max(1, min(page, total_pages))
    items = q.limit(PAGE_SIZE).offset((page - 1) * PAGE_SIZE).all()

    header_text = f"Sizning buyurtmalaringiz — sahifa {page}/{total_pages}"
    nav_kb = _build_nav("my_orders", page, total_pages, extra=str(client_id))

    key = (chat_id, f"my_orders:{client_id}")
    prev = _sent_messages.get(key)
    if prev:
        for mid in prev.get("item_ids", []):
            try:
                await bot.delete_message(chat_id=chat_id, message_id=mid)
            except Exception:
                pass

    header_id = None
    try:
        if edit_query is not None:
            await edit_query.edit_message_text(header_text, reply_markup=InlineKeyboardMarkup(nav_kb))
            header_id = edit_query.message.message_id
        else:
            resp = await bot.send_message(chat_id=chat_id, text=header_text, reply_markup=InlineKeyboardMarkup(nav_kb))
            header_id = getattr(resp, 'message_id', None)
    except Exception:
        try:
            resp = await bot.send_message(chat_id=chat_id, text=header_text, reply_markup=InlineKeyboardMarkup(nav_kb))
            header_id = getattr(resp, 'message_id', None)
        except Exception:
            header_id = None

    item_msg_ids = []
    for o in items:
        total_steps = len(o.steps)
        done = sum(1 for s in o.steps if s.status == "done")
        created = o.created_at.strftime("%Y-%m-%d") if o.created_at else "N/A"
        status_map = {
            "running": "Bajarilyapti",
            "created": "Hali boshlanmadi",
            "completed": "Ish yakunlandi",
        }
        uz_status = status_map.get(getattr(o, 'status', None), getattr(o, 'status', None) or "Noma'lum")
        lines = [f"#{o.id} Holati: {uz_status}", f"Bajarilgan ishlar: {done}/{total_steps}", f"Ish boshlangan vaqt: {created}"]
        if getattr(o, 'name', None):
            lines.append(f"Nomi: {o.name}")
        kb = [[InlineKeyboardButton("Buyurtma statusi", callback_data=f"order_status:{o.id}" )]]
        mid = await _send_message_and_get_id(bot, chat_id, "\n".join(lines), InlineKeyboardMarkup(kb))
        if mid is not None:
            item_msg_ids.append(mid)

    _sent_messages[key] = {"header_id": header_id, "item_ids": item_msg_ids}


async def my_tasks_page(session, chat_id, bot, worker_id: int, page: int = 1, edit_query=None):
    logger.info("pagination.my_tasks_page called chat=%s worker_id=%s page=%s", chat_id, worker_id, page)
    q = session.query(OrderStep).filter(OrderStep.assigned_to_id == worker_id, OrderStep.status.in_( ["assigned", "in_progress"])).order_by(OrderStep.order_id, OrderStep.position)
    total = q.count()
    if total == 0:
        await _send_or_edit(bot, chat_id, "Sizda joriy vazifalar yo'q.", edit_query=edit_query)
        return
    total_pages = (total + PAGE_SIZE - 1) // PAGE_SIZE
    page = max(1, min(page, total_pages))
    items = q.limit(PAGE_SIZE).offset((page - 1) * PAGE_SIZE).all()

    header_text = f"Sizning vazifalaringiz — sahifa {page}/{total_pages}"
    nav_kb = _build_nav("my_tasks", page, total_pages, extra=str(worker_id))

    key = (chat_id, f"my_tasks:{worker_id}")
    prev = _sent_messages.get(key)
    if prev:
        for mid in prev.get("item_ids", []):
            try:
                await bot.delete_message(chat_id=chat_id, message_id=mid)
            except Exception:
                pass

    header_id = None
    try:
        if edit_query is not None:
            await edit_query.edit_message_text(header_text, reply_markup=InlineKeyboardMarkup(nav_kb))
            header_id = edit_query.message.message_id
        else:
            resp = await bot.send_message(chat_id=chat_id, text=header_text, reply_markup=InlineKeyboardMarkup(nav_kb))
            header_id = getattr(resp, 'message_id', None)
    except Exception:
        try:
            resp = await bot.send_message(chat_id=chat_id, text=header_text, reply_markup=InlineKeyboardMarkup(nav_kb))
            header_id = getattr(resp, 'message_id', None)
        except Exception:
            header_id = None

    item_msg_ids = []
    for t in items:
        try:
            client_name = t.order.client.name if t.order and t.order.client else str(t.order.client_id)
        except Exception:
            client_name = str(getattr(t, 'order_id', 'N/A'))
        order_name = getattr(t.order, 'name', '') or ''
        order_description = getattr(t.order, 'description', '') or ''
        instruction_text = getattr(t, 'instruction_text', '') or ''
        text = f"Mijoz: {client_name}\nNomi: {order_name}\nTavsifi: {order_description}\n{instruction_text}"
        kb = [[InlineKeyboardButton("Tugatish", callback_data=f"worker_complete:{t.id}" )]]
        mid = await _send_message_and_get_id(bot, chat_id, text, InlineKeyboardMarkup(kb))
        if mid is not None:
            item_msg_ids.append(mid)

    _sent_messages[key] = {"header_id": header_id, "item_ids": item_msg_ids}


async def pending_steps_page(session, chat_id, bot, page: int = 1, edit_query=None):
    logger.info("pagination.pending_steps_page called chat=%s page=%s", chat_id, page)
    q = session.query(OrderStep).filter(OrderStep.status == "pending").order_by(OrderStep.order_id, OrderStep.position)
    total = q.count()
    if total == 0:
        await _send_or_edit(bot, chat_id, "Mavjud bosqichlar yo'q.", edit_query=edit_query)
        return
    total_pages = (total + PAGE_SIZE - 1) // PAGE_SIZE
    page = max(1, min(page, total_pages))
    items = q.limit(PAGE_SIZE).offset((page - 1) * PAGE_SIZE).all()

    header_text = f"Kutilayotgan bosqichlar — sahifa {page}/{total_pages}"
    nav_kb = _build_nav("pending_steps", page, total_pages)

    key = (chat_id, "pending_steps")
    prev = _sent_messages.get(key)
    if prev:
        for mid in prev.get("item_ids", []):
            try:
                await bot.delete_message(chat_id=chat_id, message_id=mid)
            except Exception:
                pass

    header_id = None
    try:
        if edit_query is not None:
            await edit_query.edit_message_text(header_text, reply_markup=InlineKeyboardMarkup(nav_kb))
            header_id = edit_query.message.message_id
        else:
            resp = await bot.send_message(chat_id=chat_id, text=header_text, reply_markup=InlineKeyboardMarkup(nav_kb))
            header_id = getattr(resp, 'message_id', None)
    except Exception:
        try:
            resp = await bot.send_message(chat_id=chat_id, text=header_text, reply_markup=InlineKeyboardMarkup(nav_kb))
            header_id = getattr(resp, 'message_id', None)
        except Exception:
            header_id = None

    item_msg_ids = []
    for s in items:
        try:
            client_name = s.order.client.name if s.order and s.order.client else str(s.order.client_id)
        except Exception:
            client_name = str(getattr(s, 'order_id', 'N/A'))
        order_name = getattr(s.order, 'name', '') or ''
        order_description = getattr(s.order, 'description', '') or ''
        instruction_text = getattr(s, 'instruction_text', '') or ''
        text = f"Mijoz: {client_name}\nNomi: {order_name}\nTavsifi: {order_description}\n{instruction_text}"
        kb = [[InlineKeyboardButton("Olish", callback_data=f"worker_take:{s.id}" )]]
        mid = await _send_message_and_get_id(bot, chat_id, text, InlineKeyboardMarkup(kb))
        if mid is not None:
            item_msg_ids.append(mid)

    _sent_messages[key] = {"header_id": header_id, "item_ids": item_msg_ids}


async def select_clients_for_order(session, chat_id, bot, page: int = 1, edit_query=None):
    q = session.query(User).filter(User.role == "client", User.approved == True)
    total = q.count()
    if total == 0:
        await _send_or_edit(bot, chat_id, "Hozircha tasdiqlangan mijozlar yo'q.", edit_query=edit_query)
        return
    total_pages = (total + PAGE_SIZE - 1) // PAGE_SIZE
    page = max(1, min(page, total_pages))
    items = q.order_by(User.id).limit(PAGE_SIZE).offset((page - 1) * PAGE_SIZE).all()

    header_text = f"Mijozni tanlang — sahifa {page}/{total_pages}"
    nav_kb = _build_nav("select_clients", page, total_pages)

    key = (chat_id, "select_clients")
    prev = _sent_messages.get(key)
    if prev:
        for mid in prev.get("item_ids", []):
            try:
                await bot.delete_message(chat_id=chat_id, message_id=mid)
            except Exception:
                pass

    header_id = None
    try:
        if edit_query is not None:
            await edit_query.edit_message_text(header_text, reply_markup=InlineKeyboardMarkup(nav_kb))
            header_id = edit_query.message.message_id
        else:
            resp = await bot.send_message(chat_id=chat_id, text=header_text, reply_markup=InlineKeyboardMarkup(nav_kb))
            header_id = getattr(resp, 'message_id', None)
    except Exception:
        try:
            resp = await bot.send_message(chat_id=chat_id, text=header_text, reply_markup=InlineKeyboardMarkup(nav_kb))
            header_id = getattr(resp, 'message_id', None)
        except Exception:
            header_id = None

    item_msg_ids = []
    for c in items:
        label = c.name if c.name else str(c.telegram_id)
        text = f"{label} ({c.telegram_id})"
        kb = [[InlineKeyboardButton("Tanlash", callback_data=f"create_order:client:{c.telegram_id}")]]
        mid = await _send_message_and_get_id(bot, chat_id, text, InlineKeyboardMarkup(kb))
        if mid is not None:
            item_msg_ids.append(mid)

    _sent_messages[key] = {"header_id": header_id, "item_ids": item_msg_ids}


async def select_templates_for_order(session, chat_id, bot, page: int = 1, edit_query=None):
    q = session.query(Template)
    total = q.count()
    if total == 0:
        await _send_or_edit(bot, chat_id, "Hozircha shablonlar mavjud emas.", edit_query=edit_query)
        return
    total_pages = (total + PAGE_SIZE - 1) // PAGE_SIZE
    page = max(1, min(page, total_pages))
    items = q.order_by(Template.id).limit(PAGE_SIZE).offset((page - 1) * PAGE_SIZE).all()
    lines = [f"Shablonni tanlang — sahifa {page}/{total_pages}"]
    kb = []
    for t in items:
        lines.append(f"[{t.id}] {t.name}")
        kb.append([InlineKeyboardButton(f"[{t.id}] {t.name}", callback_data=f"create_order:template:{t.id}")])
    kb.extend(_build_nav("select_templates_for_order", page, total_pages))
    await _send_or_edit(bot, chat_id, "\n".join(lines), reply_markup=InlineKeyboardMarkup(kb), edit_query=edit_query)


async def select_templates_for_add_step(session, chat_id, bot, page: int = 1, edit_query=None):
    q = session.query(Template)
    total = q.count()
    if total == 0:
        await _send_or_edit(bot, chat_id, "Hozircha shablonlar mavjud emas.", edit_query=edit_query)
        return
    total_pages = (total + PAGE_SIZE - 1) // PAGE_SIZE
    page = max(1, min(page, total_pages))
    items = q.order_by(Template.id).limit(PAGE_SIZE).offset((page - 1) * PAGE_SIZE).all()
    lines = [f"Shablonni tanlang (qadam qo'shish) — sahifa {page}/{total_pages}"]
    kb = []
    for t in items:
        lines.append(f"[{t.id}] {t.name}")
        kb.append([InlineKeyboardButton(f"[{t.id}] {t.name}", callback_data=f"add_step:template:{t.id}")])
    kb.extend(_build_nav("select_templates_for_add_step", page, total_pages))
    await _send_or_edit(bot, chat_id, "\n".join(lines), reply_markup=InlineKeyboardMarkup(kb), edit_query=edit_query)


async def select_users_for_roles(session, chat_id, bot, page: int = 1, edit_query=None):
    logger.info("pagination.select_users_for_roles called chat=%s page=%s", chat_id, page)
    q = session.query(User)
    total = q.count()
    if total == 0:
        await _send_or_edit(bot, chat_id, "Foydalanuvchilar mavjud emas.", edit_query=edit_query)
        return
    total_pages = (total + PAGE_SIZE - 1) // PAGE_SIZE
    page = max(1, min(page, total_pages))
    items = q.order_by(User.id).limit(PAGE_SIZE).offset((page - 1) * PAGE_SIZE).all()

    header_text = f"Foydalanuvchilar — sahifa {page}/{total_pages}"
    nav_kb = _build_nav("select_users_for_roles", page, total_pages)

    key = (chat_id, "select_users_for_roles")
    # delete previously sent per-item messages for this chat/view
    prev = _sent_messages.get(key)
    if prev:
        for mid in prev.get("item_ids", []):
            try:
                await bot.delete_message(chat_id=chat_id, message_id=mid)
            except Exception:
                pass

    # update or send header (the message that holds navigation)
    header_id = None
    try:
        if edit_query is not None:
            await edit_query.edit_message_text(header_text, reply_markup=InlineKeyboardMarkup(nav_kb))
            header_id = edit_query.message.message_id
        else:
            resp = await bot.send_message(chat_id=chat_id, text=header_text, reply_markup=InlineKeyboardMarkup(nav_kb))
            header_id = getattr(resp, 'message_id', None)
    except Exception:
        try:
            resp = await bot.send_message(chat_id=chat_id, text=header_text, reply_markup=InlineKeyboardMarkup(nav_kb))
            header_id = getattr(resp, 'message_id', None)
        except Exception:
            header_id = None

    # send each item as its own message with per-item inline buttons so buttons appear right under the item
    item_msg_ids = []
    for u in items:
        text = f"tg={u.telegram_id} id={u.id}\nname={u.name if u.name else ''}\nrole={u.role}"
        kb = [[
            InlineKeyboardButton("Direktor", callback_data=f"set_role:{u.telegram_id}:director"),
            InlineKeyboardButton("Ishchi", callback_data=f"set_role:{u.telegram_id}:worker"),
            InlineKeyboardButton("Mijoz", callback_data=f"set_role:{u.telegram_id}:client"),
        ]]
        try:
            sent = await bot.send_message(chat_id=chat_id, text=text, reply_markup=InlineKeyboardMarkup(kb))
            item_msg_ids.append(getattr(sent, 'message_id', None))
        except Exception as e:
            logger.exception("Failed to send per-item message chat=%s user=%s error=%s", chat_id, u.telegram_id, e)
            try:
                sent = await bot.send_message(chat_id=chat_id, text=text)
                item_msg_ids.append(getattr(sent, 'message_id', None))
            except Exception:
                pass

    # store mapping so we can cleanup on next page change
    _sent_messages[key] = {"header_id": header_id, "item_ids": [m for m in item_msg_ids if m is not None]}
