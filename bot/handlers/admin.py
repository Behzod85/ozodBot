import logging
import os
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from models import SessionLocal, User, Template, TemplateStep, Order, Process
from .utils import is_director
from . import pagination

logger = logging.getLogger(__name__)


async def become_director(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message is None:
        return
    user = update.message.from_user
    session = SessionLocal()
    try:
        director = session.query(User).filter(User.role == "director", User.approved == True).first()
        if director:
            await update.message.reply_text("Direktor allaqachon tayinlangan.")
            return
        db_user = session.query(User).filter(User.telegram_id == user.id).first()
        if not db_user:
            db_user = User(telegram_id=user.id, name=user.full_name, role="director", approved=True)
            session.add(db_user)
        else:
            db_user.role = "director"
            db_user.approved = True
        session.commit()
        await update.message.reply_text("Siz direktor (admin) etib tayinlandingiz.")
    finally:
        session.close()


async def show_orders_web(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message is None:
        return
    caller = update.message.from_user
    session = SessionLocal()
    try:
        if not is_director(session, caller.id):
            await update.message.reply_text("Faqat direktor buyurtmalarni ko'rishi mumkin.")
            return
        web_url = os.getenv('WEB_UI_URL') or 'http://localhost:5000/orders'
        # Telegram may reject local or non-routable http URLs in inline keyboard buttons
        # (e.g. http://localhost). For such URLs, send a plain text link instead
        # which Telegram will auto-link in the client.
        lower = web_url.lower()
        is_local = (
            'localhost' in lower
            or lower.startswith('http://127.')
            or lower.startswith('http://10.')
            or lower.startswith('http://192.168.')
            or lower.startswith('http://172.')
        )
        if is_local:
            await update.message.reply_text(f"Buyurtmalarni ko'rish: {web_url}")
        else:
            kb = InlineKeyboardMarkup([[InlineKeyboardButton("Ochish", url=web_url)]])
            await update.message.reply_text(f"Buyurtmalarni ko'rish: {web_url}", reply_markup=kb)
        return
    finally:
        session.close()


async def set_template_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message is None:
        return
    caller = update.message.from_user
    session = SessionLocal()
    try:
        if not is_director(session, caller.id):
            await update.message.reply_text("Faqat direktor shablon nomlarini o'zgartirishi mumkin.")
            return
        pending = context.user_data.get("pending_template_rename")
        if not pending:
            await update.message.reply_text("Kutilayotgan shablon nomini o'zgartirish operatsiyasi yo'q. Ro'yxatdagi shablon yonidagi 'Qayta nomlash' tugmasini bosing.")
            return
        if len(context.args) < 1:
            await update.message.reply_text("Foydalanish: /set_template_name <yangi_nomi>")
            return
        new_name = " ".join(context.args).strip()
        try:
            tid = int(pending)
        except Exception:
            await update.message.reply_text("Noto'g'ri kutilayotgan shablon idsi.")
            context.user_data.pop("pending_template_rename", None)
            return
        tpl = session.query(Template).filter(Template.id == tid).first()
        if not tpl:
            await update.message.reply_text("Shablon topilmadi.")
            context.user_data.pop("pending_template_rename", None)
            return
        old = tpl.name
        tpl.name = new_name
        session.commit()
        await update.message.reply_text(f"Shablon nomi '{old}' dan '{new_name}' ga o'zgartirildi.")
        context.user_data.pop("pending_template_rename", None)
    finally:
        session.close()


async def pending_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message is None:
        return
    caller = update.message.from_user
    session = SessionLocal()
    try:
        if not is_director(session, caller.id):
            await update.message.reply_text("Faqat direktor arizalarni ko'rishi mumkin.")
            return
        await pagination.pending_users_page(session, update.message.chat.id, context.bot, page=1)
    finally:
        session.close()


async def list_workers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message is None:
        return
    caller = update.message.from_user
    session = SessionLocal()
    try:
        if not is_director(session, caller.id):
            await update.message.reply_text("Faqat direktor ishchilar ro'yxatini ko'rishi mumkin.")
            return
        await pagination.workers_page(session, update.message.chat.id, context.bot, page=1)
    finally:
        session.close()


async def list_clients(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message is None:
        return
    caller = update.message.from_user
    session = SessionLocal()
    try:
        if not is_director(session, caller.id):
            await update.message.reply_text("Faqat direktor mijozlar ro'yxatini ko'rishi mumkin.")
            return
        await pagination.clients_page(session, update.message.chat.id, context.bot, page=1)
    finally:
        session.close()


async def list_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message is None:
        return
    caller = update.message.from_user
    session = SessionLocal()
    try:
        if not is_director(session, caller.id):
            await update.message.reply_text("Faqat direktor buyurtmalarni ko'rishi mumkin.")
            return
        # show paginated list of all orders
        await pagination.orders_page(session, update.message.chat.id, context.bot, page=1)
    finally:
        session.close()


async def show_usage(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message is None:
        return
    mapping = {
        "Shablon yaratish": "/create_template <name>",
        "Qadam qo'shish": "/add_step <template_id> | <instruction> | <notification>",
        "Buyurtma yaratish": "/create_order <client_tg_id> <template_id> | <name> | <description>",
        "Buyurtmani boshlash": "/start_order <order_id>",
        "Direktor tayinlash": "/appoint_director <telegram_id>",
    }
    text = update.message.text.strip()
    # interactive pipeline for creating orders
    if text == "Buyurtma yaratish":
        caller = update.message.from_user
        session = SessionLocal()
        try:
            if not is_director(session, caller.id):
                await update.message.reply_text("Faqat direktor buyurtma yaratishi mumkin.")
                return
            # show paginated client selector
            await pagination.select_clients_for_order(session, update.message.chat.id, context.bot, page=1)
            return
        finally:
            session.close()
    # interactive pipeline for adding a PROCESS (global qadam)
    if text == "Qadam qo'shish":
        caller = update.message.from_user
        session = SessionLocal()
        try:
            if not is_director(session, caller.id):
                await update.message.reply_text("Faqat direktor qadam qo'shishi mumkin.")
                return
            # start a simple pipeline to add a reusable process
            context.user_data["add_process"] = {"stage": "instruction"}
            await update.message.reply_text("Iltimos, qadam uchun ko'rsatma kiriting:")
            return
        finally:
            session.close()
    # interactive pipeline for creating a template (new flow)
    if text == "Shablon yaratish":
        caller = update.message.from_user
        session = SessionLocal()
        try:
            if not is_director(session, caller.id):
                await update.message.reply_text("Faqat direktor shablon yaratishi mumkin.")
                return
            # start interactive create_template pipeline: ask for name
            context.user_data["create_template"] = {"stage": "name"}
            await update.message.reply_text("Iltimos, yangi shablon uchun nom kiriting:")
            return
        finally:
            session.close()
    # show list of processes for director
    if text == "Qadamlar":
        caller = update.message.from_user
        session = SessionLocal()
        try:
            if not is_director(session, caller.id):
                await update.message.reply_text("Faqat direktor qadamlarni ko'rishi mumkin.")
                return
            await pagination.processes_page(session, update.message.chat.id, context.bot, page=1)
            return
        finally:
            session.close()
    # role assignment flow
    if text == "Rol tayinlash":
        caller = update.message.from_user
        session = SessionLocal()
        try:
            if not is_director(session, caller.id):
                await update.message.reply_text("Faqat direktor rollarni o'zgartirishi mumkin.")
                return
            # show paginated user list with role buttons
            await pagination.select_users_for_roles(session, update.message.chat.id, context.bot, page=1)
            return
        finally:
            session.close()
    # interactive list of created orders to start
    if text == "Buyurtmani boshlash":
        caller = update.message.from_user
        session = SessionLocal()
        try:
            if not is_director(session, caller.id):
                await update.message.reply_text("Faqat direktor buyurtmani boshlashi mumkin.")
                return
            # show paginated created orders with Boshlash button
            await pagination.orders_created_page(session, update.message.chat.id, context.bot, page=1)
            return
        finally:
            session.close()
    if text in mapping:
        await update.message.reply_text(mapping[text])
    else:
        await update.message.reply_text("Bu buyruq uchun maslahat yo'q.")


async def approve(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message is None:
        return
    # approve command handler (/approve <telegram_id> <role>)
    caller = update.message.from_user
    session = SessionLocal()
    try:
        if not is_director(session, caller.id):
            await update.message.reply_text("Faqat direktor foydalanuvchilarni tasdiqlashi mumkin.")
            return
        args = context.args
        if len(args) < 2:
            await update.message.reply_text("Foydalanish: /approve <telegram_id> <role>")
            return
        tg_id = int(args[0])
        role = args[1]
        u = session.query(User).filter(User.telegram_id == tg_id).first()
        if not u:
            await update.message.reply_text("Foydalanuvchi topilmadi. U /start orqali ro'yxatdan o'tishi kerak.")
            return
        if role == "client":
            u.role = "client"
            u.approved = True
        elif role == "worker":
            u.role = "worker"
            u.approved = True
        elif role == "director":
            u.role = "director"
            u.approved = True
        else:
            await update.message.reply_text("Noma'lum rol. Ruxsat etilgan: client, worker, director")
            return
        session.commit()
        await update.message.reply_text(f"Foydalanuvchi {u.name} ({u.telegram_id}) {u.role} sifatida tasdiqlandi.")
        try:
            await context.bot.send_message(chat_id=u.telegram_id, text=f"Sizning arizangiz tasdiqlandi. Siz — {u.role}.")
        except Exception:
            logger.warning("Foydalanuvchini to'g'ridan-to'g'ri xabardor qilib bo'lmadi")
    finally:
        session.close()


async def appoint_director(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message is None:
        return
    caller = update.message.from_user
    session = SessionLocal()
    try:
        if not is_director(session, caller.id):
            await update.message.reply_text("Faqat direktor boshqa direktorni tayinlashi mumkin.")
            return
        if len(context.args) < 1:
            await update.message.reply_text("Foydalanish: /appoint_director <telegram_id>")
            return
        try:
            tg_id = int(context.args[0])
        except ValueError:
            await update.message.reply_text("Noto'g'ri telegram_id.")
            return
        u = session.query(User).filter(User.telegram_id == tg_id).first()
        if not u:
            await update.message.reply_text("Foydalanuvchi topilmadi. U /start orqali ro'yxatdan o'tishi kerak.")
            return
        u.role = "director"
        u.approved = True
        session.commit()
        await update.message.reply_text(f"Foydalanuvchi {u.name} ({u.telegram_id}) direktor etib tayinlandi.")
        try:
            await context.bot.send_message(chat_id=u.telegram_id, text="Siz direktor etib tayinlandingiz.")
        except Exception:
            logger.warning("Yangi direktorga xabar yuborib bo'lmadi")
    finally:
        session.close()


async def set_worker_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message is None:
        return
    caller = update.message.from_user
    session = SessionLocal()
    try:
        if not is_director(session, caller.id):
            await update.message.reply_text("Faqat direktor ishchilar ismlarini o'zgartirishi mumkin.")
            return
        pending = context.user_data.get("pending_rename")
        if not pending:
            await update.message.reply_text("Kutilayotgan qayta nomlash operatsiyasi mavjud emas. Ro'yxatdagi foydalanuvchi yonidagi 'Qayta nomlash' tugmasini bosing.")
            return
        if len(context.args) < 1:
            await update.message.reply_text("Foydalanish: /set_worker_name <yangi_ism> yoki /set_client_name <yangi_ism>")
            return
        new_name = " ".join(context.args).strip()
        # pending can be int (legacy) or dict {'tg':..., 'role':...}
        if isinstance(pending, dict):
            tg = pending.get("tg")
            role = pending.get("role")
        else:
            tg = pending
            role = "worker"
        u = session.query(User).filter(User.telegram_id == tg).first()
        if not u:
            await update.message.reply_text("Foydalanuvchi topilmadi.")
            context.user_data.pop("pending_rename", None)
            return
        old_name = u.name
        u.name = new_name
        session.commit()
        await update.message.reply_text(f"Foydalanuvchi ismi {old_name} ({tg}) {new_name} ga o'zgartirildi.")
        # notify only if worker (preserve previous behavior). For clients, do NOT notify per request.
        if role == "worker":
            try:
                await context.bot.send_message(chat_id=tg, text=f"Sizning akkauntingiz: ismingiz {new_name} ga o'zgartirildi.")
            except Exception:
                logger.warning("Ishchini ism o'zgarishi haqida xabardor qilib bo'lmadi")
        context.user_data.pop("pending_rename", None)
    finally:
        session.close()


async def handle_text_for_rename(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # accept plain text as new name if director has pending_rename
    if update.message is None:
        return
    user = update.message.from_user
    session = SessionLocal()
    try:
        if not is_director(session, user.id):
            return
        # handle interactive create_order free-text stages first
        create_state = context.user_data.get("create_order")
        if create_state:
            stage = create_state.get("stage")
            text_val = update.message.text.strip()
            # name stage
            if stage == "name":
                if text_val.lower() in ("skip", "-"):
                    create_state["name"] = None
                else:
                    create_state["name"] = text_val
                create_state["stage"] = "description"
                context.user_data["create_order"] = create_state
                await update.message.reply_text("Iltimos, buyurtma tavsifini kiriting (kerak bo'lmasa 'skip' yoki '-' deb yozing):")
                return
            # description stage -> create order
            if stage == "description":
                if text_val.lower() in ("skip", "-"):
                    create_state["description"] = None
                else:
                    create_state["description"] = text_val
                # perform creation
                client_tg = create_state.get("client_tg")
                template_id = create_state.get("template_id")
                client = session.query(User).filter(User.telegram_id == client_tg, User.approved == True).first()
                if not client:
                    await update.message.reply_text("Mijoz topilmadi yoki tasdiqlanmagan.")
                    context.user_data.pop("create_order", None)
                    return
                tpl_check = session.query(TemplateStep).filter(TemplateStep.template_id == template_id).first()
                if not tpl_check:
                    await update.message.reply_text("Shablon topilmadi yoki bo'sh.")
                    context.user_data.pop("create_order", None)
                    return
                order = Order(client_id=client.id, template_id=template_id, status="created", name=create_state.get("name"), description=create_state.get("description"))
                session.add(order)
                session.commit()
                msg = f"Buyurtma yaratildi id={order.id}, mijoz {client.name} uchun."
                if order.name:
                    msg += f" Nomi: {order.name}."
                if order.description:
                    msg += f" Tavsifi: {order.description}."
                await update.message.reply_text(msg)
                context.user_data.pop("create_order", None)
                return
        # interactive create_template pipeline handling
        create_tpl_state = context.user_data.get("create_template")
        if create_tpl_state:
            stage = create_tpl_state.get("stage")
            text_val = update.message.text.strip()
            if stage == "name":
                if not text_val:
                    await update.message.reply_text("Nomi bo'sh bo'lishi mumkin emas.")
                    return
                tpl = Template(name=text_val)
                session.add(tpl)
                session.commit()
                context.user_data["create_template"] = {"stage": "selecting", "template_id": tpl.id, "selected": []}
                await pagination.select_processes_for_template(session, update.message.chat.id, context.bot, template_id=tpl.id, page=1, context=context)
                return

        # interactive add_process pipeline handling (create reusable Process)
        add_proc = context.user_data.get("add_process")
        if add_proc:
            stage = add_proc.get("stage")
            text_val = update.message.text.strip()
            if stage == "instruction":
                if text_val.lower() in ("skip", "-"):
                    add_proc["instruction"] = None
                else:
                    add_proc["instruction"] = text_val
                add_proc["stage"] = "notification"
                context.user_data["add_process"] = add_proc
                await update.message.reply_text("Iltimos, xabarnoma matnini kiriting (kerak bo'lmasa 'skip' yoki '-' deb yozing):")
                return
            if stage == "notification":
                if text_val.lower() in ("skip", "-"):
                    notification = None
                else:
                    notification = text_val
                proc = Process(instruction_text=add_proc.get("instruction"), notification_text=notification)
                session.add(proc)
                session.commit()
                await update.message.reply_text(f"Qadam yaratildi id={proc.id}.")
                context.user_data.pop("add_process", None)
                return

        # interactive add_step pipeline handling
        add_state = context.user_data.get("add_step")
        if add_state:
            stage = add_state.get("stage")
            text_val = update.message.text.strip()
            # instruction stage
            if stage == "instruction":
                if text_val.lower() in ("skip", "-"):
                    add_state["instruction"] = None
                else:
                    add_state["instruction"] = text_val
                add_state["stage"] = "notification"
                context.user_data["add_step"] = add_state
                await update.message.reply_text("Iltimos, xabarnoma matnini kiriting (kerak bo'lmasa 'skip' yoki '-' deb yozing):")
                return
            # notification stage -> create template step
            if stage == "notification":
                if text_val.lower() in ("skip", "-"):
                    notification = None
                else:
                    notification = text_val
                template_id = add_state.get("template_id")
                tpl = session.query(Template).filter(Template.id == template_id).first()
                if not tpl:
                    await update.message.reply_text("Shablon topilmadi yoki bo'sh.")
                    context.user_data.pop("add_step", None)
                    return
                max_pos = session.query(TemplateStep).filter(TemplateStep.template_id == tpl.id).count()
                # create a reusable process entry and reference it from the template step
                proc = Process(instruction_text=add_state.get("instruction"), notification_text=notification)
                session.add(proc)
                session.flush()
                step = TemplateStep(template_id=tpl.id, position=max_pos + 1, process_id=proc.id)
                session.add(step)
                session.commit()
                await update.message.reply_text(f"Qadam shablonga {tpl.id} {step.position}-pozitsiya (id={step.id}) sifatida qo'shildi.")
                context.user_data.pop("add_step", None)
                return
        # pending process rename (edit instruction_text | notification_text)
        pending_proc = context.user_data.get("pending_process_rename")
        if pending_proc:
            new_val = update.message.text.strip()
            parts = [p.strip() for p in new_val.split("|")]
            instr = parts[0] if parts else ""
            notif = parts[1] if len(parts) > 1 else None
            try:
                pid = int(pending_proc)
            except Exception:
                await update.message.reply_text("Noto'g'ri kutilayotgan qadam idsi.")
                context.user_data.pop("pending_process_rename", None)
                return
            proc = session.query(Process).filter(Process.id == pid).first()
            if not proc:
                await update.message.reply_text("Qadam topilmadi.")
                context.user_data.pop("pending_process_rename", None)
                return
            proc.instruction_text = instr
            proc.notification_text = notif
            session.commit()
            await update.message.reply_text(f"Qadam {pid} yangilandi.")
            context.user_data.pop("pending_process_rename", None)
            return
        # first handle pending template rename if present
        pending_tpl = context.user_data.get("pending_template_rename")
        if pending_tpl:
            new_name = update.message.text.strip()
            if not new_name:
                await update.message.reply_text("Ism bo'sh bo'lishi mumkin emas.")
                return
            try:
                tid = int(pending_tpl)
            except Exception:
                await update.message.reply_text("Noto'g'ri kutilayotgan shablon idsi.")
                context.user_data.pop("pending_template_rename", None)
                return
            tpl = session.query(Template).filter(Template.id == tid).first()
            if not tpl:
                await update.message.reply_text("Shablon topilmadi.")
                context.user_data.pop("pending_template_rename", None)
                return
            old = tpl.name
            tpl.name = new_name
            session.commit()
            await update.message.reply_text(f"Shablon nomi '{old}' dan '{new_name}' ga o'zgartirildi.")
            context.user_data.pop("pending_template_rename", None)
            return

        pending = context.user_data.get("pending_rename")
        if not pending:
            return
        new_name = update.message.text.strip()
        if not new_name:
            await update.message.reply_text("Ism bo'sh bo'lishi mumkin emas.")
            return
        # legacy int or dict
        if isinstance(pending, dict):
            tg = pending.get("tg")
            role = pending.get("role")
        else:
            tg = pending
            role = "worker"
        u = session.query(User).filter(User.telegram_id == tg).first()
        if not u:
            await update.message.reply_text("Foydalanuvchi topilmadi.")
            context.user_data.pop("pending_rename", None)
            return
        old_name = u.name
        u.name = new_name
        session.commit()
        await update.message.reply_text(f"Foydalanuvchi ismi {old_name} ({tg}) {new_name} ga o'zgartirildi.")
        # notify only workers
        if role == "worker":
            try:
                await context.bot.send_message(chat_id=tg, text=f"Sizning tizimdagi ismingiz o'zgartirildi: {new_name}")
            except Exception:
                logger.warning("Ishchini ism o'zgarishi haqida xabardor qilib bo'lmadi")
        context.user_data.pop("pending_rename", None)
    finally:
        session.close()
