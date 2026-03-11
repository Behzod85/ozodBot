import logging
import datetime
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from models import (
    SessionLocal,
    User,
    Template,
    TemplateStep,
    Order,
    OrderStep,
)
from .utils import is_director
from . import pagination

logger = logging.getLogger(__name__)


async def callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query is None:
        return
    await query.answer()
    data = query.data or ""
    user = query.from_user
    session = SessionLocal()
    try:
        existing = session.query(User).filter(User.telegram_id == user.id).first()

        if data == "register_client":
            if existing:
                await query.edit_message_text("Siz allaqachon ro'yxatdan o'tgansiz yoki ariza yuborilgan.")
                return
            u = User(telegram_id=user.id, name=user.full_name, role="client", approved=False)
            session.add(u)
            session.commit()
            await query.edit_message_text("Mijozni ro'yxatga olish uchun ariza direktorga yuborildi.")
            return

        if data == "register_worker":
            if existing:
                await query.edit_message_text("Siz allaqachon ro'yxatdan o'tgansiz yoki ariza yuborilgan.")
                return
            u = User(telegram_id=user.id, name=user.full_name, role="worker", approved=False)
            session.add(u)
            session.commit()
            await query.edit_message_text("Ishchini ro'yxatga olish uchun ariza direktorga yuborildi.")
            return

        # cmd: shortcuts (director/non-director views)
        if data and data.startswith("cmd:"):
            parts = data.split(":", 2)
            cmd = parts[1] if len(parts) > 1 else ""
            arg = parts[2] if len(parts) > 2 else None

            if cmd == "pending_users":
                if not is_director(session, query.from_user.id):
                    await query.answer("Faqat direktor arizalarni ko'rishi mumkin.")
                    return
                await pagination.pending_users_page(session, query.message.chat.id, context.bot, page=1, edit_query=query)
                await query.answer()
                return

            if cmd == "list_templates":
                is_dir = is_director(session, query.from_user.id)
                await pagination.templates_page(session, query.message.chat.id, context.bot, page=1, is_director=is_dir, edit_query=query)
                await query.answer()
                return

            if cmd == "list_workers":
                await pagination.workers_page(session, query.message.chat.id, context.bot, page=1, edit_query=query)
                await query.answer()
                return

            if cmd == "list_clients":
                await pagination.clients_page(session, query.message.chat.id, context.bot, page=1, edit_query=query)
                await query.answer()
                return

            if cmd == "my_orders":
                db_user = session.query(User).filter(User.telegram_id == query.from_user.id).first()
                if not db_user or db_user.role != "client":
                    await context.bot.send_message(chat_id=query.message.chat.id, text="Faqat mijoz o'z buyurtmalarini ko'rishi mumkin.")
                    return
                await pagination.my_orders_page(session, query.message.chat.id, context.bot, client_id=db_user.id, page=1, edit_query=query)
                await query.answer()
                return

            if cmd == "my_tasks":
                db_user = session.query(User).filter(User.telegram_id == query.from_user.id).first()
                if not db_user or db_user.role != "worker":
                    await context.bot.send_message(chat_id=query.message.chat.id, text="Faqat ishchi o'z vazifalarini ko'rishi mumkin.")
                    return
                await pagination.my_tasks_page(session, query.message.chat.id, context.bot, worker_id=db_user.id, page=1, edit_query=query)
                await query.answer()
                return

            if cmd == "pickup":
                db_user = session.query(User).filter(User.telegram_id == query.from_user.id, User.approved == True).first()
                if not db_user or db_user.role != "worker":
                    await context.bot.send_message(chat_id=query.message.chat.id, text="Faqat tasdiqlangan ishchi vazifalarni olishi mumkin.")
                    return
                await pagination.pending_steps_page(session, query.message.chat.id, context.bot, page=1, edit_query=query)
                await query.answer()
                return

            if cmd == "usage" and arg:
                usage_map = {
                    "create_template": "/create_template <name>",
                    "add_step": "/add_step <template_id> | <instruction> | <notification>",
                    "create_order": "/create_order <client_tg_id> <template_id> | <name> | <description>",
                    "start_order": "/start_order <order_id>",
                    "appoint_director": "/appoint_director <telegram_id>",
                    "pickup": "/pickup",
                    "complete": "/complete <order_step_id>",
                    "order_status": "/order_status <order_id>",
                }
                text = usage_map.get(arg, "Bu buyruq uchun ko'rsatma mavjud emas.")
                await context.bot.send_message(chat_id=query.message.chat.id, text=text)
                await query.answer()
                return

        # paginated view navigation
        if data and data.startswith("page:"):
            parts = data.split(":")
            # formats: page:view:page  OR page:view:extra:page
            if len(parts) == 3:
                _, view, page_str = parts
                extra = None
            elif len(parts) == 4:
                _, view, extra, page_str = parts
            else:
                await query.answer()
                return
            try:
                page_num = int(page_str)
            except Exception:
                await query.answer()
                return

            # route to pagination helpers
            if view == "pending_users":
                await pagination.pending_users_page(session, query.message.chat.id, context.bot, page=page_num, edit_query=query)
                await query.answer()
                return
            if view == "list_workers":
                await pagination.workers_page(session, query.message.chat.id, context.bot, page=page_num, edit_query=query)
                await query.answer()
                return
            if view == "list_clients":
                await pagination.clients_page(session, query.message.chat.id, context.bot, page=page_num, edit_query=query)
                await query.answer()
                return
            if view == "list_templates":
                await pagination.templates_page(session, query.message.chat.id, context.bot, page=page_num, is_director=is_director(session, query.from_user.id), edit_query=query)
                await query.answer()
                return
            if view == "list_processes":
                await pagination.processes_page(session, query.message.chat.id, context.bot, page=page_num, edit_query=query)
                await query.answer()
                return
            if view == "select_processes_for_template" and extra is not None:
                try:
                    tpl_id = int(extra)
                except Exception:
                    await query.answer()
                    return
                await pagination.select_processes_for_template(session, query.message.chat.id, context.bot, template_id=tpl_id, page=page_num, edit_query=query, context=context)
                await query.answer()
                return
            if view == "orders_created":
                await pagination.orders_created_page(session, query.message.chat.id, context.bot, page=page_num, edit_query=query)
                await query.answer()
                return
            if view == "my_orders" and extra is not None:
                try:
                    client_id = int(extra)
                except Exception:
                    await query.answer()
                    return
                await pagination.my_orders_page(session, query.message.chat.id, context.bot, client_id=client_id, page=page_num, edit_query=query)
                await query.answer()
                return
            if view == "my_tasks" and extra is not None:
                try:
                    worker_id = int(extra)
                except Exception:
                    await query.answer()
                    return
                await pagination.my_tasks_page(session, query.message.chat.id, context.bot, worker_id=worker_id, page=page_num, edit_query=query)
                await query.answer()
                return
            if view == "pending_steps":
                await pagination.pending_steps_page(session, query.message.chat.id, context.bot, page=page_num, edit_query=query)
                await query.answer()
                return
            if view == "select_clients":
                await pagination.select_clients_for_order(session, query.message.chat.id, context.bot, page=page_num, edit_query=query)
                await query.answer()
                return
            if view == "select_templates_for_order":
                await pagination.select_templates_for_order(session, query.message.chat.id, context.bot, page=page_num, edit_query=query)
                await query.answer()
                return
            if view == "select_templates_for_add_step":
                await pagination.select_templates_for_add_step(session, query.message.chat.id, context.bot, page=page_num, edit_query=query)
                await query.answer()
                return
            if view == "select_users_for_roles":
                await pagination.select_users_for_roles(session, query.message.chat.id, context.bot, page=page_num, edit_query=query)
                await query.answer()
                return

        # interactive create-order callbacks
        if data and data.startswith("create_order:"):
            parts = data.split(":")
            action = parts[1] if len(parts) > 1 else None
            if action == "cancel":
                try:
                    await query.edit_message_text("Buyurtma yaratish bekor qilindi.")
                except Exception:
                    await context.bot.send_message(chat_id=query.message.chat.id, text="Buyurtma yaratish bekor qilindi.")
                context.user_data.pop("create_order", None)
                return

            if action == "client" and len(parts) > 2:
                try:
                    client_tg = int(parts[2])
                except Exception:
                    await query.edit_message_text("Noto'g'ri mijoz identifikatori.")
                    return
                context.user_data["create_order"] = {"client_tg": client_tg}
                tpls = session.query(Template).all()
                if not tpls:
                    try:
                        await query.edit_message_text("Hozircha shablonlar mavjud emas. Avval shablon yarating.")
                    except Exception:
                        await context.bot.send_message(chat_id=query.message.chat.id, text="Hozircha shablonlar mavjud emas. Avval shablon yarating.")
                    return
                kb = []
                for t in tpls:
                    kb.append([InlineKeyboardButton(f"[{t.id}] {t.name}", callback_data=f"create_order:template:{t.id}")])
                kb.append([InlineKeyboardButton("Bekor qilish", callback_data="create_order:cancel")])
                try:
                    await query.edit_message_text("Shablonni tanlang:", reply_markup=InlineKeyboardMarkup(kb))
                except Exception:
                    await context.bot.send_message(chat_id=query.message.chat.id, text="Shablonni tanlang:", reply_markup=InlineKeyboardMarkup(kb))
                return

            if action == "template" and len(parts) > 2:
                try:
                    template_id = int(parts[2])
                except Exception:
                    await query.edit_message_text("Noto'g'ri shablon identifikatori.")
                    return
                co = context.user_data.get("create_order")
                if not co or "client_tg" not in co:
                    await query.edit_message_text("Oldin mijozni tanlang.")
                    return
                co["template_id"] = template_id
                co["stage"] = "name"
                context.user_data["create_order"] = co
                try:
                    await query.edit_message_text("Iltimos, buyurtma nomini kiriting (kerak bo'lmasa 'skip' yoki '-' deb yozing):")
                except Exception:
                    await context.bot.send_message(chat_id=query.message.chat.id, text="Iltimos, buyurtma nomini kiriting (kerak bo'lmasa 'skip' yoki '-' deb yozing):")
                return

        # interactive add_step callbacks
        if data and data.startswith("add_step:"):
            parts = data.split(":")
            action = parts[1] if len(parts) > 1 else None
            if action == "cancel":
                try:
                    await query.edit_message_text("Qadam qo'shish bekor qilindi.")
                except Exception:
                    await context.bot.send_message(chat_id=query.message.chat.id, text="Qadam qo'shish bekor qilindi.")
                context.user_data.pop("add_step", None)
                return

        # process management callbacks (director)
        if data and data.startswith("process_delete:"):
            try:
                pid = int(data.split(":", 1)[1])
            except Exception:
                await query.edit_message_text("Noto'g'ri ma'lumot formati.")
                return
            if not is_director(session, query.from_user.id):
                await query.edit_message_text("Faqat direktor qadamlarni o'chirishi mumkin.")
                return
            # don't delete if used in any template
            used = session.query(TemplateStep).filter(TemplateStep.process_id == pid).count()
            if used > 0:
                await query.edit_message_text("Bu qadam bir yoki bir nechta shablonlarda ishlatilmoqda. Avval shablonlardan o'chiring.")
                return
            from models import Process
            p = session.query(Process).filter(Process.id == pid).first()
            if not p:
                await query.edit_message_text("Qadam topilmadi.")
                return
            session.delete(p)
            session.commit()
            await query.edit_message_text(f"Qadam {pid} o'chirildi.")
            return

        if data and data.startswith("process_rename:"):
            try:
                pid = int(data.split(":", 1)[1])
            except Exception:
                await query.edit_message_text("Noto'g'ri ma'lumot formati.")
                return
            if not is_director(session, query.from_user.id):
                await query.edit_message_text("Faqat direktor qadamlarni qayta nomlashi mumkin.")
                return
            context.user_data["pending_process_rename"] = pid
            await query.edit_message_text("Iltimos, yangi ko'rsatma va xabarnoma kiriting format: <instruction_text> | <notification_text> (agar xabarnoma o'zgarmasa '-' kiriting)")
            return

        # select process for template creation flow
        if data and data.startswith("select_process:"):
            parts = data.split(":")
            if len(parts) < 3:
                await query.answer()
                return
            try:
                tpl_id = int(parts[1])
                pid = int(parts[2])
                # optional page argument: select_process:tpl_id:proc_id[:page]
                page_num = int(parts[3]) if len(parts) > 3 else 1
            except Exception:
                await query.answer()
                return
            if not is_director(session, query.from_user.id):
                await query.answer("Faqat direktor shablon yaratishi mumkin.")
                return
            ct = context.user_data.get("create_template")
            if not ct or ct.get("template_id") != tpl_id:
                await query.answer("Shablon yaratish jarayoni topilmadi. Iltimos, avval nom kiriting.")
                return
            sel = ct.get("selected", [])
            # toggle selection
            if pid in sel:
                sel.remove(pid)
            else:
                sel.append(pid)
            context.user_data["create_template"]["selected"] = sel

            # Edit only the originating per-item message in-place to avoid
            # touching other item messages (prevents mass delete/resend).
            try:
                from models import Process as ModelProcess
                p = session.query(ModelProcess).filter(ModelProcess.id == pid).first()
            except Exception:
                p = None

            sel_mark = " ✅" if pid in sel else ""
            instr = getattr(p, 'instruction_text', '') or ''
            noti = getattr(p, 'notification_text', '') or ''
            text = f"[{pid}] {instr[:80]}{sel_mark}\nnotify={noti[:60]}"
            btn_text = "✅ Tanlangan" if pid in sel else "Tanlash"
            # preserve page in callback so further toggles keep same page
            cb = f"select_process:{tpl_id}:{pid}:{page_num}"
            kb = InlineKeyboardMarkup([[InlineKeyboardButton(btn_text, callback_data=cb)]])

            try:
                # edit the message that triggered the callback (per-item message)
                await query.edit_message_text(text, reply_markup=kb)
            except Exception as e:
                err = str(e)
                # if message is not modified, treat as success
                if "not modified" in err.lower() or "message is not modified" in err.lower():
                    pass
                else:
                    # fallback: try deleting the old message and sending a replacement
                    try:
                        if query.message:
                            await query.message.delete()
                    except Exception:
                        pass
                    try:
                        await context.bot.send_message(chat_id=query.message.chat.id if query.message else query.from_user.id, text=text, reply_markup=kb)
                    except Exception:
                        logger.exception("Failed to update per-item message for select_process %s", pid)

            await query.answer()
            return

        if data and data.startswith("create_template:finish"):
            parts = data.split(":")
            if len(parts) < 3:
                await query.edit_message_text("Noto'g'ri ma'lumot formati.")
                return
            try:
                tpl_id = int(parts[2])
            except Exception:
                await query.edit_message_text("Noto'g'ri shablon identifikatori.")
                return
            if not is_director(session, query.from_user.id):
                await query.edit_message_text("Faqat direktor shablon yaratishi mumkin.")
                return
            ct = context.user_data.get("create_template")
            if not ct or ct.get("template_id") != tpl_id:
                await query.edit_message_text("Shablon yaratish jarayoni topilmadi yoki tugatishga tayyor emas.")
                return
            selected = ct.get("selected", [])
            if not selected:
                await query.edit_message_text("Hech qanday qadam tanlanmadi. Avval qadamlarni tanlang.")
                return
            tpl = session.query(Template).filter(Template.id == tpl_id).first()
            if not tpl:
                await query.edit_message_text("Shablon topilmadi.")
                context.user_data.pop("create_template", None)
                return
            # create template steps in the chosen order
            pos = session.query(TemplateStep).filter(TemplateStep.template_id == tpl.id).count()
            for pid in selected:
                pos += 1
                step = TemplateStep(template_id=tpl.id, position=pos, process_id=pid)
                session.add(step)
            session.commit()
            context.user_data.pop("create_template", None)
            await query.edit_message_text(f"Shablon {tpl.id} uchun {len(selected)} ta qadam tanlandi va qo'shildi.")
            return
            

        # set role callback (assign role to a telegram user)
        if data and data.startswith("set_role:"):
            parts = data.split(":")
            if len(parts) < 3:
                await query.edit_message_text("Noto'g'ri ma'lumot formati.")
                return
            try:
                tg = int(parts[1])
            except Exception:
                await query.edit_message_text("Noto'g'ri telegram identifikatori.")
                return
            role = parts[2]
            if not is_director(session, query.from_user.id):
                await query.edit_message_text("Faqat direktor rollarni o'zgartirishi mumkin.")
                return
            u = session.query(User).filter(User.telegram_id == tg).first()
            if not u:
                await query.edit_message_text("Foydalanuvchi topilmadi.")
                return
            if role not in ("director", "worker", "client"):
                await query.edit_message_text("Noma'lum rol.")
                return
            u.role = role
            u.approved = True
            session.commit()
            # Notify the user with role-specific Uzbek messages
            try:
                if role == "client":
                    await context.bot.send_message(chat_id=u.telegram_id, text=(
                        "Hurmatli mijoz bizga ishonch bildirganingiz uchun tashakkur! "
                        "Siz buyurtmalaringiz holatini ushbu botimiz orqali kuzatib borishingiz mumkin."
                    ))
                else:
                    # worker or director
                    role_label = "ishchi" if role == "worker" else "direktor"
                    await context.bot.send_message(chat_id=u.telegram_id, text=f"Sizning arizangiz tasdiqlandi. Siz - {role_label}.")
            except Exception:
                logger.warning("Foydalanuvchini to'g'ridan-to'g'ri xabardor qilib bo'lmadi.")
            role_uz = {"director": "direktor", "worker": "ishchi", "client": "mijoz"}[role]
            await query.edit_message_text(f"Foydalanuvchi {u.name} ({u.telegram_id}) roli {role_uz} ga o'zgartirildi.")
            return

        # approve/reject callbacks (director actions)
        if data and data.startswith("approve:"):
            try:
                tg = int(data.split(":", 1)[1])
            except Exception:
                await query.edit_message_text("Noto'g'ri ma'lumot formati.")
                return
            u = session.query(User).filter(User.telegram_id == tg).first()
            if not u:
                await query.edit_message_text("Foydalanuvchi topilmadi.")
                return
            u.approved = True
            session.commit()
            try:
                await context.bot.send_message(chat_id=u.telegram_id, text=f"Sizning arizangiz tasdiqlandi. Siz — {u.role}.")
            except Exception:
                logger.warning("Foydalanuvchini bevosita xabardor qilib bo'lmadi.")
            await query.edit_message_text(f"Foydalanuvchi {u.name} ({u.telegram_id}) {u.role} sifatida tasdiqlandi.")
            return

        if data and data.startswith("reject:"):
            try:
                tg = int(data.split(":", 1)[1])
            except Exception:
                await query.edit_message_text("Noto'g'ri ma'lumot formati.")
                return
            u = session.query(User).filter(User.telegram_id == tg).first()
            if not u:
                await query.edit_message_text("Foydalanuvchi topilmadi.")
                return
            session.delete(u)
            session.commit()
            try:
                await context.bot.send_message(chat_id=tg, text="Sizning arizangiz direktor tomonidan rad etildi.")
            except Exception:
                logger.warning("Foydalanuvchini rad etilishi haqida xabardor qilib bo'lmadi.")
            await query.edit_message_text(f"Foydalanuvchi {tg} rad etildi va o'chirildi.")
            return

        # director-only deletes/rename
        if data and data.startswith("worker_delete:"):
            try:
                tg = int(data.split(":", 1)[1])
            except Exception:
                await query.edit_message_text("Noto'g'ri ma'lumot formati.")
                return
            if not is_director(session, query.from_user.id):
                await query.edit_message_text("Faqat direktor ishchilarni o'chirishi mumkin.")
                return
            u = session.query(User).filter(User.telegram_id == tg).first()
            if not u:
                await query.edit_message_text("Foydalanuvchi topilmadi.")
                return
            if u.role != "worker":
                await query.edit_message_text("Faqat ishchi hisobini o'chirish mumkin.")
                return
            steps = session.query(OrderStep).filter(OrderStep.assigned_to_id == u.id).all()
            for s in steps:
                s.assigned_to_id = None
                s.status = "pending"
            session.delete(u)
            session.commit()
            try:
                await context.bot.send_message(chat_id=tg, text="Sizning ishchi hisobingiz direktor tomonidan o'chirildi.")
            except Exception:
                logger.warning("Ishchi o'chirilgani haqida xabar berib bo'lmadi")
            await query.edit_message_text(f"Ishchi {tg} o'chirildi.")
            return

        if data and data.startswith("client_delete:"):
            try:
                tg = int(data.split(":", 1)[1])
            except Exception:
                await query.edit_message_text("Noto'g'ri ma'lumot formati.")
                return
            if not is_director(session, query.from_user.id):
                await query.edit_message_text("Faqat direktor mijozlarni o'chirishi mumkin.")
                return
            u = session.query(User).filter(User.telegram_id == tg).first()
            if not u:
                await query.edit_message_text("Foydalanuvchi topilmadi.")
                return
            if u.role != "client":
                await query.edit_message_text("Faqat mijoz hisobini o'chirish mumkin.")
                return
            orders_count = session.query(Order).filter(Order.client_id == u.id).count()
            if orders_count > 0:
                await query.edit_message_text("Buyurtmalari mavjud bo'lgan mijozni o'chirib bo'lmaydi.")
                return
            session.delete(u)
            session.commit()
            await query.edit_message_text(f"Mijoz {tg} o'chirildi.")
            return

        if data and data.startswith("worker_rename:"):
            try:
                tg = int(data.split(":", 1)[1])
            except Exception:
                await query.edit_message_text("Noto'g'ri ma'lumot formati.")
                return
            if not is_director(session, query.from_user.id):
                await query.edit_message_text("Faqat direktor ishchilarni qayta nomlashi mumkin.")
                return
            u = session.query(User).filter(User.telegram_id == tg).first()
            if not u:
                await query.edit_message_text("Foydalanuvchi topilmadi.")
                return
            context.user_data["pending_rename"] = {"tg": tg, "role": "worker"}
            await query.edit_message_text(f"Ishchi {u.name} uchun yangi ismni kiriting yoki /set_worker_name <yangi_ism> buyrug'idan foydalaning.")
            return

        if data and data.startswith("client_rename:"):
            try:
                tg = int(data.split(":", 1)[1])
            except Exception:
                await query.edit_message_text("Noto'g'ri ma'lumot formati.")
                return
            if not is_director(session, query.from_user.id):
                await query.edit_message_text("Faqat direktor mijozlarni qayta nomlashi mumkin.")
                return
            u = session.query(User).filter(User.telegram_id == tg).first()
            if not u:
                await query.edit_message_text("Foydalanuvchi topilmadi.")
                return
            context.user_data["pending_rename"] = {"tg": tg, "role": "client"}
            await query.edit_message_text(f"Mijoz {u.name} uchun yangi ismni kiriting yoki /set_client_name <yangi_ism> buyrug'idan foydalaning.")
            return

        if data and data.startswith("worker_complete:"):
            try:
                sid = int(data.split(":", 1)[1])
            except Exception:
                await query.edit_message_text("Noto'g'ri ma'lumot formati.")
                return
            db_user = session.query(User).filter(User.telegram_id == query.from_user.id, User.approved == True).first()
            if not db_user or db_user.role != "worker":
                await query.edit_message_text("Faqat tasdiqlangan ishchi bosqichlarni yakunlashi mumkin.")
                return
            step = session.query(OrderStep).filter(OrderStep.id == sid).first()
            if not step or step.status == "done":
                await query.edit_message_text("Bosqich topilmadi yoki allaqachon bajarilgan.")
                return
            if step.assigned_to_id != db_user.id:
                await query.edit_message_text("Siz bu bosqichga tayinlanmagansiz. Avval /pickup orqali oling yoki 'Olish' tugmasini bosing.")
                return
            from .workers import finalize_step
            await finalize_step(session, step, db_user.telegram_id, context)
            await query.edit_message_text(f"Bosqich {step.id} bajarildi deb belgilandi.")
            return

        if data and data.startswith("worker_take:"):
            try:
                sid = int(data.split(":", 1)[1])
            except Exception:
                await query.edit_message_text("Noto'g'ri ma'lumot formati.")
                return
            db_user = session.query(User).filter(User.telegram_id == query.from_user.id, User.approved == True).first()
            if not db_user or db_user.role != "worker":
                await query.edit_message_text("Faqat tasdiqlangan ishchi bosqichlarni olishi mumkin.")
                return
            step = session.query(OrderStep).filter(OrderStep.id == sid).first()
            if not step:
                await query.edit_message_text("Bosqich topilmadi.")
                return
            if step.status != "pending":
                await query.edit_message_text("Bosqich allaqachon olingan yoki mavjud emas.")
                return
            step.assigned_to_id = db_user.id
            step.status = "assigned"
            session.commit()
            try:
                await context.bot.send_message(chat_id=db_user.telegram_id, text=f"Siz buyurtma {step.order_id} ning {step.id} bosqichini oldingiz.\nKo'rsatma: {step.instruction_text}\nKo'rish: /my_tasks")
            except Exception:
                logger.warning("Bosqich tayinlanganligi haqida ishchini xabardor qilib bo'lmadi")
            try:
                await query.edit_message_text(f"Bosqich {step.id} siz tomonidan olindi (ishchi {db_user.name}).")
            except Exception:
                pass
            return

        if data and data.startswith("template_delete:"):
            try:
                tid = int(data.split(":", 1)[1])
            except Exception:
                await query.edit_message_text("Noto'g'ri ma'lumot formati.")
                return
            if not is_director(session, query.from_user.id):
                await query.edit_message_text("Faqat direktor shablonlarni o'chirishi mumkin.")
                return
            tpl = session.query(Template).filter(Template.id == tid).first()
            if not tpl:
                await query.edit_message_text("Shablon topilmadi.")
                return
            orders_count = session.query(Order).filter(Order.template_id == tpl.id).count()
            if orders_count > 0:
                others = session.query(Template).filter(Template.id != tpl.id).all()
                if not others:
                    await query.edit_message_text("Shablon buyurtmalarda ishlatilmoqda, ammo boshqa shablonlar yo'q. O'chirishdan oldin boshqa shablon yarating.")
                    return
                # Show other templates as targets for reassigning existing orders.
            # remove any TemplateStep rows tied to this template (defensive; cascade also set on relationship)
            try:
                session.query(TemplateStep).filter(TemplateStep.template_id == tpl.id).delete(synchronize_session=False)
            except Exception:
                # best-effort: ignore deletion errors here, template deletion will still proceed
                pass
            session.delete(tpl)
            session.commit()
            await query.edit_message_text(f"Shablon {tid} o'chirildi.")
            return

        if data and data.startswith("template_delete_cancel:"):
            await query.edit_message_text("O'chirish operatsiyasi bekor qilindi.")
            return

        if data and data.startswith("reassign_template:"):
            parts = data.split(":")
            if len(parts) < 3:
                await query.edit_message_text("Noto'g'ri ma'lumot formati.")
                return
            try:
                old_tid = int(parts[1])
                new_tid = int(parts[2])
            except Exception:
                await query.edit_message_text("Shablon identifikatorlari formati noto'g'ri.")
                return
            if not is_director(session, query.from_user.id):
                await query.edit_message_text("Faqat direktor buyurtmalarni boshqa shablonga o'tkazishi mumkin.")
                return
            old_tpl = session.query(Template).filter(Template.id == old_tid).first()
            new_tpl = session.query(Template).filter(Template.id == new_tid).first()
            if not old_tpl or not new_tpl:
                await query.edit_message_text("Shablonlardan biri topilmadi.")
                return
            orders = session.query(Order).filter(Order.template_id == old_tpl.id).all()
            reassigned = 0
            for o in orders:
                o.template_id = new_tpl.id
                if o.status != "running":
                    session.query(OrderStep).filter(OrderStep.order_id == o.id).delete()
                reassigned += 1
            session.query(TemplateStep).filter(TemplateStep.template_id == old_tpl.id).delete()
            session.delete(old_tpl)
            session.commit()
            await query.edit_message_text(f"Shablon {old_tid} o'chirildi. {reassigned} ta buyurtma yangi shablon {new_tpl.id} ga o'tkazildi.")
            return

        if data and data.startswith("template_rename:"):
            try:
                tid = int(data.split(":", 1)[1])
            except Exception:
                await query.edit_message_text("Noto'g'ri ma'lumot formati.")
                return
            if not is_director(session, query.from_user.id):
                await query.edit_message_text("Faqat direktor shablonlarni qayta nomlashi mumkin.")
                return
            tpl = session.query(Template).filter(Template.id == tid).first()
            if not tpl:
                await query.edit_message_text("Shablon topilmadi.")
                return
            context.user_data["pending_template_rename"] = tid
            await query.edit_message_text(f"Shablon '{tpl.name}' uchun yangi nomni kiriting yoki /set_template_name <yangi_nomi> buyrug'idan foydalaning.")
            return

        if data and data.startswith("order_status:"):
            try:
                oid = int(data.split(":", 1)[1])
            except Exception:
                await query.edit_message_text("Noto'g'ri ma'lumot formati.")
                return
            o = session.query(Order).filter(Order.id == oid).first()
            if not o:
                await query.edit_message_text("Buyurtma topilmadi.")
                return
            status_map = {
                "running": "Bajarilyapti",
                "created": "Hali boshlanmadi",
                "completed": "Ish yakunlandi",
            }
            uz_status = status_map.get(getattr(o, 'status', None), getattr(o, 'status', "Noma'lum"))
            task_status_map = { # pending, assigned, in_progress, done
                "pending": "Hali boshlanmadi",
                "assigned": "Jarayonda",
                "in_progress": "Jarayonda",
                "done": "Ish yakunlandi",
            }
            lines = [f"Buyurtma #{o.id}\nHolati: {uz_status}"]
            if getattr(o, 'name', None):
                lines.append(f"Nomi: {o.name}")
            for s in o.steps:
                uz_task_status = task_status_map.get(getattr(s, 'status', None), getattr(s, 'status', "Noma'lum"))
                lines.append(f"Bosqich: {s.position}\n  Jarayon: {s.instruction_text}\n  Holati: {uz_task_status}")
            # include the order's client id in the callback so the back button
            # always navigates to that client's orders (uses pagination handler)
            kb = [[InlineKeyboardButton("Orqaga", callback_data=f"page:my_orders:{o.client_id}:1")]]
            try:
                await query.edit_message_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(kb))
            except Exception:
                await context.bot.send_message(chat_id=query.message.chat.id, text="\n".join(lines), reply_markup=InlineKeyboardMarkup(kb))
            await query.answer()
            return

        if data and data.startswith("start_order:"):
            try:
                oid = int(data.split(":", 1)[1])
            except Exception:
                await query.edit_message_text("Noto'g'ri ma'lumot formati.")
                return
            if not is_director(session, query.from_user.id):
                await query.edit_message_text("Faqat direktor buyurtmani ishga tushirishi mumkin.")
                return
            o = session.query(Order).filter(Order.id == oid).first()
            if not o:
                await query.edit_message_text("Buyurtma topilmadi.")
                return
            if o.status != "created":
                await query.edit_message_text("Buyurtma allaqachon ishga tushirilgan yoki yakunlangan.")
                return
            template_steps = session.query(TemplateStep).filter(TemplateStep.template_id == o.template_id).order_by(TemplateStep.position).all()
            for s in template_steps:
                instr = getattr(s, 'instruction_text', None)
                notif = getattr(s, 'notification_text', None)
                if getattr(s, 'process', None):
                    instr = getattr(s.process, 'instruction_text', instr)
                    notif = getattr(s.process, 'notification_text', notif)
                os = OrderStep(order_id=o.id, template_step_id=s.id, position=s.position, role=getattr(s, 'role', 'worker'), instruction_text=instr, notification_text=notif, status="pending")
                session.add(os)
            o.status = "running"
            o.started_at = datetime.datetime.utcnow()
            session.commit()

            pending_count = session.query(OrderStep).filter(OrderStep.order_id == o.id).count()
            if pending_count > 0:
                workers = session.query(User).filter(User.role == "worker", User.approved == True).all()
                for w in workers:
                    try:
                        order_name = getattr(o, 'name', None)
                        if order_name:
                            await context.bot.send_message(chat_id=w.telegram_id, text=f"Buyurtma #{o.id} uchun {pending_count} ta bosqich mavjud — {order_name}. Keyingi bosqichni olish uchun /pickup buyrug'idan foydalaning.")
                        else:
                            await context.bot.send_message(chat_id=w.telegram_id, text=f"Buyurtma #{o.id} uchun {pending_count} ta bosqich mavjud. Keyingi bosqichni olish uchun /pickup buyrug'idan foydalaning.")
                    except Exception:
                        pass

            # notify client that the order has started
            try:
                client = o.client
                if client and getattr(client, 'telegram_id', None):
                    if getattr(o, 'name', None):
                        await context.bot.send_message(chat_id=client.telegram_id, text=f"Assalomu alaykum! Buyurtmangiz muvaffaqiyatli ro‘yxatga olindi. {o.name} bo‘yicha ishlab chiqarish jarayoni boshlandi. Biz ishga kirishdik!")
                    else:
                        await context.bot.send_message(chat_id=client.telegram_id, text=f"Assalomu alaykum! Buyurtmangiz muvaffaqiyatli ro‘yxatga olindi. Buyurtma #{o.id} bo‘yicha ishlab chiqarish jarayoni boshlandi. Biz ishga kirishdik!")
            except Exception:
                logger.exception("Failed to send order-start notification to client")

            result_text = f"Buyurtma {o.id} ishga tushirildi, bosqichlar soni: {pending_count}."
            try:
                await query.edit_message_text(result_text)
            except Exception:
                await context.bot.send_message(chat_id=query.message.chat.id, text=result_text)
            return

        await query.edit_message_text("Noma'lum buyruq.")
    finally:
        session.close()
