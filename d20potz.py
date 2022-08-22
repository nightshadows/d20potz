#! /usr/bin/env python3
# -*- coding: utf-8 -*-

import collections
import configparser
import leveldb
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
DB = leveldb.LevelDB(CONFIG.db_location)

# Enable logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)

logger = logging.getLogger(__name__)

###############################################################################################

def getCurrentPlayerId(chat_id):
    current_player_id_key = "current_player_{}".format(chat_id)
    current_player_id = DB.Get(current_player_id_key)
    return current_player_id

def getPlayerById(chat_id, player_id):
    player_list_key = "player_list_{}".format(chat_id)
    player_list = DB.Get(player_list_key).split()
    return player_list[player_id]

def getNextPlayerId(chat_id):
    player_list_key = "player_list_{}".format(chat_id)
    player_list = DB.Get(player_list_key).split()
    current_player_id_key = "current_player_{}".format(chat_id)
    current_player_id = DB.Get(current_player_id_key)
    next_player_id = (int(current_player_id) + 1) % len(player_list)
    return next_player_id

def setCurrentPlayerId(chat_id, player_id):
    current_player_id_key = "current_player_{}".format(chat_id)
    DB.Put(current_player_id_key, player_id)

###############################################################################################

def error(bot, update, error):
    logger.warning('Update "%s" caused error "%s"' % (update, error))

def ParseArgs():
    parser = optparse.OptionParser()
    return parser.parse_args()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(chat_id=update.effective_chat.id, text="d20potz at your service!")

async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(chat_id=update.effective_chat.id, text=update.message.text)

async def endTurn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    currentPlayer = getPlayerById(getCurrentPlayerId(update.effective_chat.id))
    nextPlayerId = getNextPlayerId(update.effective_chat.id)
    setCurrentPlayerId(update.effective_chat.id, nextPlayerId)
    nextPlayer = getPlayerById(nextPlayerId)
    await context.bot.send_message(chat_id=update.effective_chat.id, text="{}'s turn ended. It is now {}'s turn.".format(currentPlayer, nextPlayer))

async def help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(chat_id=update.effective_chat.id, text="d20potz ready to help")

def d20potzbot():
    application = ApplicationBuilder().token(CONFIG.token).build()
    
    start_handler = CommandHandler('start', start)
    application.add_handler(start_handler)

    help_handler = CommandHandler('help', help)
    application.add_handler(help_handler)

    endTurn_handler = CommandHandler('endturn', endTurn)
    application.add_handler(endTurn_handler)

    echo_handler = MessageHandler(filters.TEXT & (~filters.COMMAND), echo)
    application.add_handler(echo_handler)
    
    application.run_polling()

if __name__ == "__main__":
    opt, args = ParseArgs()
    d20potzbot()