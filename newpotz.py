import asyncio
import json
import logging
import os
import traceback

from telegram import (
    Chat,
    Update,
)

from telegram.error import BadRequest

from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    filters,
    MessageHandler,
    CallbackQueryHandler,
)

from botdata import BotData
from d20potz_state_machine import PotzState
from utils import get_client_help_message, MAX_DICE
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
    return botData


async def reply(text: str, update: Update, context: ContextTypes.DEFAULT_TYPE, botData: BotData):
    message = await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=text,
        reply_markup=botData.get_inline_keyboard(),
    )

    if message:
        logger.info("Storing inline message id %s", message.message_id)
        await botData.set_inline_message_id(message.message_id, context)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    botData = parse_update(update)

    help_text = get_client_help_message()

    await reply(help_text, update, context, botData)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    botData = parse_update(update)

    start_text = "Welcome to the bot, potz!"

    await reply(start_text, update, context, botData)


async def roll_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Parse update to get bot data
    botData = parse_update(update)

    res = await botData.process("roll", context)
    return await reply(res, update, context, botData)


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    botData = parse_update(update)

    res = ""

    # Check if the callback data is a valid state
    if botData.params:
        res = await botData.process(botData.params[0], context)

    # remove the inline keyboard
    try:
        await context.bot.edit_message_reply_markup(
            chat_id=update.effective_chat.id,
            message_id=update.callback_query.message.message_id,
        )
    except BadRequest:
        pass # this will happen if we are cleaning up already deleted messages

    await reply(res, update, context, botData)


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

    roll_handler = CommandHandler("roll", roll_command)
    application.add_handler(roll_handler)

    application.add_handler(CallbackQueryHandler(button_callback))

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