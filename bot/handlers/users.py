from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import ContextTypes

from models import SessionLocal, User, Order
from . import pagination


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message is None:
        return
    user = update.message.from_user
    session = SessionLocal()
    try:
        db_user = session.query(User).filter(User.telegram_id == user.id).first()
        if db_user:
            if db_user.approved:
                # show role-specific keyboard immediately
                await update.message.reply_text(f"Siz {db_user.role} sifatida ro'yxatdan o'tgansiz.")
                await commands_handler(update, context)
            else:
                await update.message.reply_text("Sizning arizangiz direktor tomonidan tasdiqlanishini kutmoqda.")
            return

        keyboard = [
            [InlineKeyboardButton("Men mijoz", callback_data="register_client")],
            [InlineKeyboardButton("Men ishchi", callback_data="register_worker")],
        ]
        await update.message.reply_text("Xush kelibsiz! Ro'yxatdan o'tish uchun rolni tanlang:", reply_markup=InlineKeyboardMarkup(keyboard))
    finally:
        session.close()


async def my_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message is None:
        return
    user = update.message.from_user
    session = SessionLocal()
    try:
        db_u = session.query(User).filter(User.telegram_id == user.id, User.approved == True).first()
        if not db_u or db_u.role != "client":
            await update.message.reply_text("Faqat tasdiqlangan mijoz o'z buyurtmalarini ko'rishi mumkin.")
            return
        # Use the centralized pagination view so the UI matches the callback back-button
        await pagination.my_orders_page(session, update.message.chat.id, context.bot, client_id=db_u.id, page=1, edit_query=None)
    finally:
        session.close()


async def commands_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message is None:
        return
    user = update.message.from_user
    session = SessionLocal()
    try:
        u = session.query(User).filter(User.telegram_id == user.id).first()
        if not u:
            await update.message.reply_text("Siz ro'yxatdan o'tmagansiz. Ro'yxatdan o'tish uchun /start buyrug'idan foydalaning.")
            return
        if not u.approved:
            await update.message.reply_text("Sizning arizangiz direktor tomonidan tasdiqlanishini kutmoqda.")
            return
        # build inline keyboard per-role for quick navigation
        if u.role == "director":
            kb = [
                [KeyboardButton("Arizalar"), KeyboardButton("Rol tayinlash")],
                [KeyboardButton("Ishchilar"), KeyboardButton("Mijozlar")],
                [KeyboardButton("Shablonlar"), KeyboardButton("Shablon yaratish")],
                [KeyboardButton("Qadamlar"), KeyboardButton("Qadam qo'shish")],
                [KeyboardButton("Buyurtma yaratish"), KeyboardButton("Buyurtmani boshlash")],
                [KeyboardButton("Buyurtmalar")],
            ]
            reply = ReplyKeyboardMarkup(kb, resize_keyboard=True, one_time_keyboard=False)
            await update.message.reply_text("Direktor komandalari — amalni tanlang:", reply_markup=reply)
        elif u.role == "worker":
            kb = [[KeyboardButton("Bosqichni olish"), KeyboardButton("Mening vazifalarim")]]
            reply = ReplyKeyboardMarkup(kb, resize_keyboard=True, one_time_keyboard=False)
            await update.message.reply_text("Ishchi komandalari — amalni tanlang:", reply_markup=reply)
        elif u.role == "client":
            kb = [[KeyboardButton("Mening buyurtmalarim")]]
            reply = ReplyKeyboardMarkup(kb, resize_keyboard=True, one_time_keyboard=False)
            await update.message.reply_text("Mijoz komandalari — amalni tanlang:", reply_markup=reply)
        else:
            await update.message.reply_text("Rol tanilmadi. Iltimos, direktor bilan bog'laning.")
    finally:
        session.close()
