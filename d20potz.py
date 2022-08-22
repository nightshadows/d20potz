#! /usr/bin/env python3
# -*- coding: utf-8 -*-

import collections
import configparser
import leveldb
import logging
import optparse
import random
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
    current_player_id_key = "current_player_{}".format(chat_id).encode('utf-8')
    current_player_id = DB.Get(current_player_id_key)
    return int(current_player_id.decode('utf-8'))

def getPlayerById(chat_id, player_id):
    player_list_key = "player_list_{}".format(chat_id).encode('utf-8')
    player_list = DB.Get(player_list_key).decode('utf-8').split()
    return player_list[player_id]

def getNextPlayerId(chat_id):
    player_list_key = "player_list_{}".format(chat_id).encode('utf-8')
    player_list = DB.Get(player_list_key).decode('utf-8').split()
    current_player_id_key = "current_player_{}".format(chat_id).encode('utf-8')
    current_player_id = int(DB.Get(current_player_id_key).decode('utf-8'))
    next_player_id = (int(current_player_id) + 1) % len(player_list)
    return next_player_id

def setCurrentPlayerId(chat_id, player_id):
    current_player_id_key = "current_player_{}".format(chat_id).encode('utf-8')
    DB.Put(current_player_id_key, str(player_id).encode('utf-8'))

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
    currentPlayer = getPlayerById(update.effective_chat.id, getCurrentPlayerId(update.effective_chat.id))
    nextPlayerId = getNextPlayerId(update.effective_chat.id)
    setCurrentPlayerId(update.effective_chat.id, nextPlayerId)
    nextPlayer = getPlayerById(update.effective_chat.id, nextPlayerId)
    await context.bot.send_message(chat_id=update.effective_chat.id, text="{}'s turn ended. It is now {}'s turn.".format(currentPlayer, nextPlayer))

async def setPlayerList(update: Update, context: ContextTypes.DEFAULT_TYPE):
    player_list_key = "player_list_{}".format(update.effective_chat.id).encode('utf-8')
    player_list = ' '.join(update.message.text.split()[1:])
    DB.Put(player_list_key, player_list.encode('utf-8'))
    setCurrentPlayerId(update.effective_chat.id, 0)
    await context.bot.send_message(chat_id=update.effective_chat.id, text="Player list set.")

async def currentPlayer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    currentPlayer = getPlayerById(update.effective_chat.id, getCurrentPlayerId(update.effective_chat.id))
    await context.bot.send_message(chat_id=update.effective_chat.id, text="It is {}'s turn.".format(currentPlayer))

async def roll20(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(chat_id=update.effective_chat.id, text="Rolling... {}".format(random.randint(1,20)))

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

    setPlayerList_handler = CommandHandler('setplayerlist', setPlayerList)
    application.add_handler(setPlayerList_handler)

    currentPlayer_handler = CommandHandler('currentplayer', currentPlayer)
    application.add_handler(currentPlayer_handler)

    roll20_handler = CommandHandler('roll20', roll20)
    application.add_handler(roll20_handler)

    echo_handler = MessageHandler(filters.TEXT & (~filters.COMMAND), echo)
    application.add_handler(echo_handler)
    
    application.run_polling()

if __name__ == "__main__":
    opt, args = ParseArgs()
    d20potzbot()