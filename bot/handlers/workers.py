import datetime
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from models import SessionLocal, User, OrderStep, Order
from . import pagination

logger = logging.getLogger(__name__)


async def show_pending_steps(session, chat_id, bot, page: int = 1):
    """Kutilayotgan OrderStep larni chatga 'Olish' tugmalari bilan yuborish (paginated)."""
    await pagination.pending_steps_page(session, chat_id, bot, page=page)


async def pickup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message is None:
        return
    user = update.message.from_user
    session = SessionLocal()
    try:
        db_user = session.query(User).filter(User.telegram_id == user.id, User.approved == True).first()
        if not db_user or db_user.role != "worker":
            await update.message.reply_text("Faqat tasdiqlangan ishchi vazifalarni olishi mumkin.")
            return
        # Kutilayotgan barcha bosqichlarni har biri uchun "Olish" tugmasi bilan ko'rsatish
        await show_pending_steps(session, update.message.chat.id, context.bot)
    finally:
        session.close()


async def my_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message is None:
        return
    user = update.message.from_user
    session = SessionLocal()
    try:
        db_user = session.query(User).filter(User.telegram_id == user.id, User.approved == True).first()
        if not db_user or db_user.role != "worker":
            await update.message.reply_text("Faqat tasdiqlangan ishchi.")
            return
        # show only tasks assigned to this worker
        tasks = session.query(OrderStep).filter(OrderStep.assigned_to_id == db_user.id, OrderStep.status.in_( ["assigned", "in_progress"])) .order_by(OrderStep.order_id, OrderStep.position).all()
        if not tasks:
            await update.message.reply_text("Sizda joriy vazifalar yo'q.")
            return
        for t in tasks:
            try:
                if getattr(t, 'order', None) and getattr(t.order, 'client', None):
                    client_name = t.order.client.name
                elif getattr(t, 'order', None) and getattr(t.order, 'client_id', None):
                    client_name = str(t.order.client_id)
                else:
                    client_name = str(getattr(t, 'order_id', 'N/A'))
            except Exception:
                client_name = str(getattr(t, 'order_id', 'N/A'))
            order_name = getattr(t.order, 'name', '') or ''
            order_description = getattr(t.order, 'description', '') or ''
            instruction_text = getattr(t, 'instruction_text', '') or ''
            text = f"Mijoz: {client_name}\nNomi: {order_name}\nTavsifi: {order_description}\n{instruction_text}"
            kb = [[InlineKeyboardButton("Tugatish", callback_data=f"worker_complete:{t.id}" )]]
            await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb))
    finally:
        session.close()


async def complete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message is None:
        return
    user = update.message.from_user
    session = SessionLocal()
    try:
        db_user = session.query(User).filter(User.telegram_id == user.id, User.approved == True).first()
        if not db_user or db_user.role != "worker":
            await update.message.reply_text("Faqat tasdiqlangan ishchi bosqichlarni yakunlashi mumkin.")
            return
        if len(context.args) < 1:
            await update.message.reply_text("Foydalanish: /complete <order_step_id>")
            return
        step_id = int(context.args[0])
        step = session.query(OrderStep).filter(OrderStep.id == step_id).first()
        if not step:
            await update.message.reply_text("Bosqich topilmadi.")
            return
        # only assigned worker may complete the step
        if step.assigned_to_id != db_user.id:
            await update.message.reply_text("Siz ushbu bosqichga tayinlanmagansiz. Avval uni /pickup orqali oling yoki 'Olish' tugmasini bosing.")
            return
        await finalize_step(session, step, db_user.telegram_id, context)
        await update.message.reply_text(f"Bosqich {step.id} bajarildi.")
    finally:
        session.close()


async def finalize_step(session, step, completer_telegram_id, context):
    # mark this step done and record time
    now = datetime.datetime.utcnow()
    step.status = "done"
    step.completed_at = now
    # set assigned_to to completer if exists
    completer = session.query(User).filter(User.telegram_id == completer_telegram_id).first()
    if completer:
        step.assigned_to_id = completer.id
    session.commit()

    # notify client about step completion
    order = session.query(Order).filter(Order.id == step.order_id).first()
    client = None
    if order:
        client = session.query(User).filter(User.id == order.client_id).first()
        try:
                if client:
                    if getattr(order, 'name', None):
                        await context.bot.send_message(chat_id=client.telegram_id, text=f"Buyurtma #{order.id} bo'yicha yangilanish — {order.name}: {step.notification_text}")
                    else:
                        await context.bot.send_message(chat_id=client.telegram_id, text=f"Buyurtma #{order.id} bo'yicha yangilanish: {step.notification_text}")
        except Exception:
            logger.warning("Mijozga bildirishnoma jo'natib bo'lmadi")

    # assign next pending step (preserve sequential conveyor)
    next_step = session.query(OrderStep).filter(
        OrderStep.order_id == step.order_id,
        OrderStep.position > step.position,
        OrderStep.status == "pending",
    ).order_by(OrderStep.position).first()
    if next_step:
        workers = session.query(User).filter(User.role == "worker", User.approved == True).all()
        assigned = False
        for w in workers:
            busy = session.query(OrderStep).filter(OrderStep.assigned_to_id == w.id, OrderStep.status.in_( ["assigned", "in_progress"]) ).count()
            if busy == 0:
                next_step.assigned_to_id = w.id
                next_step.status = "assigned"
                session.commit()
                assigned = True
                try:
                    await context.bot.send_message(chat_id=w.telegram_id, text=f"Buyurtma #{order.id} bo'yicha yangi bosqich — qadam {next_step.position}: {next_step.instruction_text}\nBuyruq: /complete {next_step.id}")
                except Exception:
                    logger.warning("Keyingi ishchiga bildirishnoma jo'natib bo'lmadi")
                break
        if not assigned:
            # notify all workers that a new step is available (regardless of busy status)
            for w in workers:
                try:
                    await context.bot.send_message(chat_id=w.telegram_id, text=f"Buyurtma #{order.id} bo'yicha yangi bosqich mavjud — qadam {next_step.position}. Uni olish uchun /pickup buyrug'idan foydalaning.")
                except Exception:
                    logger.warning("Ishchiga mavjud bosqich haqida bildirishnoma jo'natib bo'lmadi")
    else:
        # no pending next step -> check full completion
        remaining = session.query(OrderStep).filter(OrderStep.order_id == step.order_id, OrderStep.status != "done").count()
        if remaining == 0 and order:
            order.status = "completed"
            order.completed_at = datetime.datetime.utcnow()
            session.commit()
            try:
                if client:
                    if getattr(order, 'name', None):
                        await context.bot.send_message(chat_id=client.telegram_id, text=f"Sizning buyurtmangiz #{order.id} — {order.name} to'liq yakunlandi.")
                    else:
                        await context.bot.send_message(chat_id=client.telegram_id, text=f"Sizning buyurtmangiz #{order.id} to'liq yakunlandi.")
            except Exception:
                logger.warning("Buyurtma yakunlangani haqida mijozga bildirishnoma jo'natib bo'lmadi")
