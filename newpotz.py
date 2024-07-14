import asyncio
import json
import logging
import os
import traceback

from telegram import (
    Chat,
    Update,
)

from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    filters,
    MessageHandler,
)

from botdata import BotData
from utils import get_client_help_message
from shared import setup_logging

logger = setup_logging(logging.INFO, __name__)

app = ApplicationBuilder().token(os.getenv("TELEGRAM_TOKEN")).build()
is_initialized = False


async def tg_bot_main(application, event):
    async with application:
        await application.process_update(
            Update.de_json(json.loads(event["body"]), application.bot)
        )


def parse_update(update: Update) -> BotData:
    botData = BotData(update)
    botData.sync()
    return botData


async def reply(text: str, update: Update, context: ContextTypes.DEFAULT_TYPE, botData: BotData):
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=text,
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    botData = parse_update(update)

    help_text = get_client_help_message()

    await reply(help_text, update, context, botData)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    botData = parse_update(update)

    start_text = "Welcome to the bot, potz!"

    await reply(start_text, update, context, botData)

# error handler, logs the error and sends the message to the chat if debug mode is enabled
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    import html

    from telegram.constants import ParseMode

    tb_list = traceback.format_exception(
        None, context.error, context.error.__traceback__
    )
    tb_string = "".join(tb_list)

    update_str = update.to_dict() if isinstance(update, Update) else str(update)
    message = (
        f"An exception was raised while handling an update\n"
        f"<pre>update = {html.escape(json.dumps(update_str, indent=2, ensure_ascii=False))}"
        "</pre>\n\n"
        f"<pre>context.chat_data = {html.escape(str(context.chat_data))}</pre>\n\n"
        f"<pre>context.user_data = {html.escape(str(context.user_data))}</pre>\n\n"
        f"<pre>{html.escape(tb_string)}</pre>"
    )

    logger.error(message, exc_info=context.error)


def register_handlers(application):
    help_handler = CommandHandler("help", help_command)
    application.add_handler(help_handler)

    start_handler = CommandHandler("start", start_command)
    application.add_handler(start_handler)

    application.add_error_handler(error_handler)


def lambda_handler(event, _context):
    global is_initialized # pylint: disable=global-statement
    try:
        if not is_initialized:
            register_handlers(app)
            is_initialized = True
        asyncio.run(tg_bot_main(app, event))
    except Exception as e: # pylint: disable=broad-except
        logger.error("Event handling failed", exc_info=True)
        return {"statusCode": 500, "body": str(e)}

    return {"statusCode": 200, "body": "ok"}