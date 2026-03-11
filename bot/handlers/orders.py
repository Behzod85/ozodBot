import datetime
from telegram import Update
from telegram.ext import ContextTypes

from models import SessionLocal, TemplateStep, Order, OrderStep, User


async def create_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message is None:
        return
    caller = update.message.from_user
    session = SessionLocal()
    try:
        # Support optional title and description using '|' separators:
        # /create_order <client_tg_id> <template_id> | <name> | <description>
        text = update.message.text or ""
        body = text[len("/create_order"):].strip()
        if not body:
            await update.message.reply_text("Foydalanish: /create_order <client_tg_id> <template_id> | <name> | <description>")
            return
        parts = [p.strip() for p in body.split("|")]
        first = parts[0].split()
        if len(first) < 2:
            await update.message.reply_text("Foydalanish: /create_order <client_tg_id> <template_id> | <name> | <description>")
            return
        client_tg = int(first[0])
        template_id = int(first[1])
        name = parts[1] if len(parts) > 1 and parts[1] != "" else None
        description = parts[2] if len(parts) > 2 and parts[2] != "" else None
        client = session.query(User).filter(User.telegram_id == client_tg, User.approved == True).first()
        if not client:
            await update.message.reply_text("Mijoz topilmadi yoki tasdiqlanmagan.")
            return
        tpl = session.query(TemplateStep).filter(TemplateStep.template_id == template_id).first()
        # quick existence check of template via its steps
        if not tpl:
            await update.message.reply_text("Shablon topilmadi.")
            return
        order = Order(client_id=client.id, template_id=template_id, status="created", name=name, description=description)
        session.add(order)
        session.commit()
        msg = f"Buyurtma yaratildi id={order.id}, mijoz {client.name} uchun."
        if order.name:
            msg += f" Nomi: {order.name}."
        if order.description:
            msg += f" Tavsifi: {order.description}."
        await update.message.reply_text(msg)
    finally:
        session.close()


async def start_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message is None:
        return
    session = SessionLocal()
    try:
        if len(context.args) < 1:
            await update.message.reply_text("Foydalanish: /start_order <order_id>")
            return
        order_id = int(context.args[0])
        order = session.query(Order).filter(Order.id == order_id).first()
        if not order:
            await update.message.reply_text("Buyurtma topilmadi.")
            return
        if order.status != "created":
            await update.message.reply_text("Buyurtma allaqachon ishga tushirilgan yoki yakunlangan.")
            return
        # create steps
        template_steps = session.query(TemplateStep).filter(TemplateStep.template_id == order.template_id).order_by(TemplateStep.position).all()
        for s in template_steps:
            instr = getattr(s, 'instruction_text', None)
            notif = getattr(s, 'notification_text', None)
            if getattr(s, 'process', None):
                instr = getattr(s.process, 'instruction_text', instr)
                notif = getattr(s.process, 'notification_text', notif)
            os = OrderStep(order_id=order.id, template_step_id=s.id, position=s.position, role=getattr(s, 'role', 'worker'), instruction_text=instr, notification_text=notif, status="pending")
            session.add(os)
        order.status = "running"
        order.started_at = datetime.datetime.now()
        session.commit()

        # Do NOT auto-assign steps. Keep them as pending so workers can pick up.
        pending_count = session.query(OrderStep).filter(OrderStep.order_id == order.id).count()
        if pending_count > 0:
            workers = session.query(User).filter(User.role == "worker", User.approved == True).all()
            for w in workers:
                try:
                    order_name = getattr(order, 'name', None)
                    if order_name:
                        await context.bot.send_message(chat_id=w.telegram_id, text=f"Buyurtma #{order.id} uchun {pending_count} ta bosqich mavjud — {order_name}. Keyingi bosqichni olish uchun /pickup buyrug'idan foydalaning.")
                    else:
                        await context.bot.send_message(chat_id=w.telegram_id, text=f"Buyurtma #{order.id} uchun {pending_count} ta bosqich mavjud. Keyingi bosqichni olish uchun /pickup buyrug'idan foydalaning.")
                except Exception:
                    pass

        # notify client that the order has started
        try:
            client = session.query(User).filter(User.id == order.client_id).first()
            if client and getattr(client, 'telegram_id', None):
                if getattr(order, 'name', None):
                    await context.bot.send_message(chat_id=client.telegram_id, text=f"Assalomu alaykum! Buyurtmangiz muvaffaqiyatli ro‘yxatga olindi. {order.name} bo‘yicha ishlab chiqarish jarayoni boshlandi. Biz ishga kirishdik!")
                else:
                    await context.bot.send_message(chat_id=client.telegram_id, text="Assalomu alaykum! Buyurtmangiz muvaffaqiyatli ro‘yxatga olindi. Buyurtmangiz ishlab chiqarish jarayoni boshlandi. Biz ishga kirishdik!")
        except Exception:
            pass

        await update.message.reply_text(f"Buyurtma {order.id} ishga tushirildi, bosqichlar soni: {pending_count}.")
    finally:
        session.close()


async def order_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message is None:
        return
    if len(context.args) < 1:
        await update.message.reply_text("Foydalanish: /order_status <order_id>")
        return
    order_id = int(context.args[0])
    session = SessionLocal()
    try:
        order = session.query(Order).filter(Order.id == order_id).first()
        if not order:
            await update.message.reply_text("Buyurtma topilmadi.")
            return
        lines = [f"Buyurtma #{order.id} status={order.status}"]
        if getattr(order, 'name', None):
            lines.append(f"Nomi: {order.name}")
        if getattr(order, 'description', None):
            lines.append(f"Tavsifi: {order.description}")
        for s in order.steps:
            lines.append(f"bosqich {s.position} id={s.id} rol={s.role} status={s.status} tayinlangan={s.assigned_to_id}")
        await update.message.reply_text("\n".join(lines))
    finally:
        session.close()
