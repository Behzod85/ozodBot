import os
import logging
import telegram
from dotenv import load_dotenv

load_dotenv()

from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
)

from models import init_db
from bot.handlers import (
    start,
    callback_query,
    become_director,
    pending_users,
    approve,
    appoint_director,
    my_orders,
    commands_handler,
    set_worker_name,
        set_template_name,
    handle_text_for_rename,
    create_template,
    add_step,
    list_templates,
        list_workers,
        list_clients,
        show_usage,
        show_orders_web,
    create_order,
    start_order,
    pickup,
    my_tasks,
    complete,
    order_status,
)

BOT_TOKEN = os.getenv("BOT_TOKEN")


def main():
    if not BOT_TOKEN:
        print("Xato: BOT_TOKEN muhit o'zgaruvchisini o'rnating")
        return
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)

    init_db()
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    async def _global_error_handler(update, context):
        try:
            logger.exception("Unhandled exception while handling update: %s", update)
        except Exception:
            logger.exception("Unhandled exception in error handler")
        err = getattr(context, "error", None)
        # If another getUpdates is running, stop this instance to avoid hammering Telegram
        if isinstance(err, telegram.error.Conflict):
            logger.error("Conflict detected: %s. Handling getUpdates conflict.", err)
            app_ctx = getattr(context, "application", None)
            # If application is running, try to stop it gracefully
            if app_ctx is not None and getattr(app_ctx, "running", False):
                try:
                    await app_ctx.stop()
                except Exception as e:
                    logger.exception("Error while stopping application after Conflict: %s", e)
            else:
                # Application not running (or not available) — exit process to avoid retry loops
                logger.error("Application not running; exiting process to avoid repeated getUpdates conflicts.")
                try:
                    os._exit(1)
                except Exception:
                    logger.exception("Failed to os._exit after getUpdates conflict")

    # Register a global error handler (compat: try add_error_handler, fallback to ErrorHandler)
    try:
        app.add_error_handler(_global_error_handler)
    except Exception:
        from telegram.ext import ErrorHandler

        app.add_handler(ErrorHandler(_global_error_handler))

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(callback_query))
    app.add_handler(CommandHandler("become_director", become_director))
    app.add_handler(CommandHandler("pending_users", pending_users))
    app.add_handler(CommandHandler("approve", approve))
    app.add_handler(CommandHandler("appoint_director", appoint_director))
    app.add_handler(CommandHandler("my_orders", my_orders))
    app.add_handler(CommandHandler("commands", commands_handler))
    app.add_handler(CommandHandler("help", commands_handler))
    # Message handlers to support ReplyKeyboard buttons (plain text)
    app.add_handler(MessageHandler(filters.Regex(r'^(Bosqichni olish)$') & ~filters.COMMAND, pickup))
    app.add_handler(MessageHandler(filters.Regex(r'^(Mening vazifalarim)$') & ~filters.COMMAND, my_tasks))
    app.add_handler(MessageHandler(filters.Regex(r'^(Mening buyurtmalarim)$') & ~filters.COMMAND, my_orders))
    # Director keyboard handlers
    app.add_handler(MessageHandler(filters.Regex(r'^(Arizalar)$') & ~filters.COMMAND, pending_users))
    app.add_handler(MessageHandler(filters.Regex(r'^\s*Shablonlar\s*$') & ~filters.COMMAND, list_templates))
    app.add_handler(MessageHandler(filters.Regex(r"^(Shablon yaratish|Qadam qo'shish|Buyurtma yaratish|Buyurtmani boshlash|Rol tayinlash|Qadamlar)$") & ~filters.COMMAND, show_usage))
    app.add_handler(MessageHandler(filters.Regex(r'^(Buyurtmalar)$') & ~filters.COMMAND, show_orders_web))
    app.add_handler(MessageHandler(filters.Regex(r'^(Ishchilar)$') & ~filters.COMMAND, list_workers))
    app.add_handler(MessageHandler(filters.Regex(r'^(Mijozlar)$') & ~filters.COMMAND, list_clients))
    app.add_handler(CommandHandler("set_worker_name", set_worker_name))
    app.add_handler(CommandHandler("set_template_name", set_template_name))
    app.add_handler(CommandHandler("set_client_name", set_worker_name))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_for_rename))
    app.add_handler(CommandHandler("create_template", create_template))
    app.add_handler(CommandHandler("add_step", add_step))
    app.add_handler(CommandHandler("list_templates", list_templates))
    app.add_handler(CommandHandler("create_order", create_order))
    app.add_handler(CommandHandler("start_order", start_order))
    app.add_handler(CommandHandler("pickup", pickup))
    app.add_handler(CommandHandler("my_tasks", my_tasks))
    app.add_handler(CommandHandler("complete", complete))
    app.add_handler(CommandHandler("order_status", order_status))

    print("Bot starting...")
    app.run_polling()


if __name__ == "__main__":
    main()
