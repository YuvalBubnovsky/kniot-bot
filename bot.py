import logging
import os

from telegram.ext import Application, CallbackQueryHandler, CommandHandler, MessageHandler, filters

from handlers import category_callback, handle_message, help_command, start
from messages import COMMANDS

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)


async def post_init(app):
    await app.bot.set_my_commands(COMMANDS)


def main():
    token = os.environ.get("BOT_TOKEN")
    if not token:
        raise SystemExit("Set BOT_TOKEN environment variable")
    app = Application.builder().token(token).post_init(post_init).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CallbackQueryHandler(category_callback, pattern=r"^cat:"))
    app.add_handler(MessageHandler(filters.TEXT, handle_message))
    logger.info("Bot started")
    app.run_polling()


if __name__ == "__main__":
    main()