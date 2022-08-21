#! /usr/bin/env python3
# -*- coding: utf-8 -*-

import collections
import configparser
import logging
import optparse
import sys
import telegram

from telegram import Update
from telegram.ext import filters, ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler

D20PotzBotConfiguration = collections.namedtuple("D20PotzBotConfiguration", "db_location token")
def read_configuration(configuration_file):
    from configparser import ConfigParser
    cp = ConfigParser()
    if configuration_file in cp.read([configuration_file]):
        db_location = cp.get("bot", "db_dir")
        token = cp.get("bot", "telegram_token")
        return D20PotzBotConfiguration(db_location, token)

CONFIG = read_configuration("./d20potz.cfg")

# Enable logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)

logger = logging.getLogger(__name__)

def error(bot, update, error):
    logger.warning('Update "%s" caused error "%s"' % (update, error))

def ParseArgs():
    parser = optparse.OptionParser()
    return parser.parse_args()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(chat_id=update.effective_chat.id, text="d20potz at your service!")

async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(chat_id=update.effective_chat.id, text=update.message.text)

async def help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(chat_id=update.effective_chat.id, text="d20potz ready to help")

def d20potzbot():
    application = ApplicationBuilder().token(CONFIG.token).build()
    
    start_handler = CommandHandler('start', start)
    application.add_handler(start_handler)

    help_handler = CommandHandler('help', help)
    application.add_handler(help_handler)

    echo_handler = MessageHandler(filters.TEXT & (~filters.COMMAND), echo)
    application.add_handler(echo_handler)
    
    application.run_polling()

if __name__ == "__main__":
    opt, args = ParseArgs()
    d20potzbot()