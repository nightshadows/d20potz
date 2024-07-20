import asyncio
import json
import logging
import os
import traceback

from telegram import (
    Update,
)

from telegram.error import RetryAfter

from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    CallbackQueryHandler,
)

from botdata import BotData
from d20potz_state_machine import PotzState
from utils import get_client_help_message, MAX_DICE
from shared import setup_logging, PotzRateLimitException

logger = setup_logging(logging.INFO, __name__)

app = ApplicationBuilder().token(os.getenv("TELEGRAM_TOKEN")).build()
is_initialized = False


async def tg_bot_main(application, event):
    async with application:
        await application.process_update(
            Update.de_json(json.loads(event["body"]), application.bot)
        )


async def parse_update(update: Update) -> BotData:
    botData = BotData(update)
    await botData.throttle()
    return botData


async def reply(text: str, update: Update, context: ContextTypes.DEFAULT_TYPE, botData: BotData):
    try:
        if len(text) < 60:
            # append text with whitespace to 50 chars:
            text += " " * (59 - len(text))
            text += '.'

        message = await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=text,
            reply_markup=botData.get_inline_keyboard(),
        )
    except RetryAfter:
        logger.error("Rate limited by telegram, exiting without saving", exc_info=True)
        return

    if message:
        await botData.set_inline_message_id(message.message_id, context)

    botData.save2()

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    botData = await parse_update(update, context)

    help_text = get_client_help_message()

    await reply(help_text, update, context, botData)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    botData = await parse_update(update)

    start_text = "Welcome to the bot, potz!"

    await reply(start_text, update, context, botData)


async def roll_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Parse update to get bot data
    botData = await parse_update(update)

    res = await botData.process("roll", context)
    return await reply(res, update, context, botData)


async def add_hero_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    botData = await parse_update(update)

    res = botData.add_hero(context)

    return await reply(res, update, context, botData)


async def remove_hero_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    botData = await parse_update(update)

    res = botData.remove_hero(context)

    return await reply(res, update, context, botData)


async def add_timer_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    botData = await parse_update(update)

    res = botData.add_timer(context)

    return await reply(res, update, context, botData)


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    botData = await parse_update(update)

    res = ""

    # Check if the callback data is a valid state
    if botData.params:
        res = await botData.process(botData.params[0], context)

    await reply(res, update, context, botData)


async def privacy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    botData = await parse_update(update)

    res = f"This bot does not store or process any Personal data. The only data stored is the fictional data you provide for the game, it is tied to the telegram chat ID and is stored in the database."

    return await reply(res, update, context, botData)


# error handler, logs the error and sends the message to the chat if debug mode is enabled
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if type(context.error) == PotzRateLimitException:
        # ignore rate limit exceptions, they are valid and already logged as warnings
        return

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

    add_hero_handler = CommandHandler("add_hero", add_hero_command)
    application.add_handler(add_hero_handler)

    remove_hero_handler = CommandHandler("remove_hero", remove_hero_command)
    application.add_handler(remove_hero_handler)

    add_timer_handler = CommandHandler("add_timer", add_timer_command)
    application.add_handler(add_timer_handler)

    privacy_handler = CommandHandler("privacy", privacy_command)
    application.add_handler(privacy_handler)

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