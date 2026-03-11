from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

import logging

from models import SessionLocal, Template, TemplateStep, Process
from .utils import is_director
from . import pagination

logger = logging.getLogger(__name__)


async def create_template(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message is None:
        return
    caller = update.message.from_user
    session = SessionLocal()
    try:
        # permission check is performed by caller (director command)
        name = " ".join(context.args).strip()
        if not name:
            await update.message.reply_text("Foydalanish: /create_template <name>")
            return
        t = Template(name=name, created_by=None)
        session.add(t)
        session.commit()
        await update.message.reply_text(f"Shablon yaratildi id={t.id} name={t.name}. Qadamlarni /add_step orqali qo'shishingiz mumkin")
    finally:
        session.close()


async def add_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # format: /add_step <template_id> | <instruction_text> | <notification_text>
    if update.message is None:
        return
    caller = update.message.from_user
    session = SessionLocal()
    try:
        text = update.message.text[len("/add_step"):].strip()
        if not text:
            await update.message.reply_text("Foydalanish: /add_step <template_id> | <instruction_text> | <notification_text>")
            return
        parts = [p.strip() for p in text.split("|")]
        if len(parts) < 3:
            await update.message.reply_text("Noto'g'ri format. '|' bilan ajratilgan uch qism kerak")
            return
        first = parts[0].split()
        if len(first) < 1:
            await update.message.reply_text("Birinchi blokda <template_id> bo'lishi kerak")
            return
        template_id = int(first[0])
        instruction = parts[1]
        notification = parts[2]
        tpl = session.query(Template).filter(Template.id == template_id).first()
        if not tpl:
            await update.message.reply_text("Shablon topilmadi.")
            return
        max_pos = session.query(TemplateStep).filter(TemplateStep.template_id == tpl.id).count()
        # create reusable process entry, then reference it from template step
        proc = Process(instruction_text=instruction, notification_text=notification)
        session.add(proc)
        session.flush()
        step = TemplateStep(template_id=tpl.id, position=max_pos + 1, process_id=proc.id)
        session.add(step)
        session.commit()
        await update.message.reply_text(f"Qadam shablonga {tpl.id} {step.position}-pozitsiya (id={step.id}) sifatida qo'shildi.")
    finally:
        session.close()


async def list_templates(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message is None:
        return
    session = SessionLocal()
    try:
        # use paginated templates view
        caller = update.message.from_user
        logger.info("list_templates invoked chat=%s from_user=%s text=%r", update.message.chat.id, caller.id, update.message.text)
        await pagination.templates_page(session, update.message.chat.id, context.bot, page=1, is_director=is_director(session, caller.id))
    finally:
        session.close()
