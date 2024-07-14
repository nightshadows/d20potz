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
MAX_DICE = 5


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


async def roll_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Parse update to get bot data
    botData = parse_update(update)

    # Check and validate the number of dice from the command arguments
    try:
        num_dice = int(context.args[0]) if context.args else 1
        if num_dice < 1 or num_dice > MAX_DICE:
            raise ValueError
    except (ValueError, IndexError):
        error_message = f"Invalid number of dice. Please specify a number between 1 and {MAX_DICE}."
        await reply(error_message, update, context, botData)
        return

    # Roll the dice and collect the results
    dice_results = []
    for _ in range(num_dice):
        message = await context.bot.send_dice(chat_id=botData.chat_id)
        dice_results.append(message.dice.value)

    # Prepare the result message
    dice_results_str = ", ".join(map(str, dice_results))
    res = f"Rolling {num_dice} {'die' if num_dice == 1 else 'dice'}... {dice_results_str}"

    # Reply with the result message
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