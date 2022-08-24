#! /usr/bin/env python3
# -*- coding: utf-8 -*-

import collections
import leveldb
import logging
import optparse
import os
import random
from typing import List

from telegram import Update, InputMediaPhoto
from telegram.ext import filters, ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler

D20PotzBotConfiguration = collections.namedtuple("D20PotzBotConfiguration", "db_location token cards_dir spelling order hp_defaults")
def read_configuration(secret_config, default_config):
    from configparser import ConfigParser
    cp = ConfigParser()
    if secret_config in cp.read([secret_config, default_config]):
        db_location = cp.get("bot", "db_dir")
        token = cp.get("bot", "telegram_token")
        cards_dir = cp.get("bot", "cards_dir", fallback="./cards")
        spelling = cp.items("spelling")
        order = cp.get("general", "player_list", fallback="")
        hp_defaults = cp.items("hp")
        return D20PotzBotConfiguration(db_location, token, cards_dir, spelling, order, hp_defaults)

def read_cards(cards_dir):
    cards = dict()
    for subdirname in os.listdir(cards_dir):
        if os.path.isdir(os.path.join(cards_dir, subdirname)):
            cards[subdirname] = list()
            for filename in os.listdir(os.path.join(cards_dir, subdirname)):
                if filename.lower().endswith(".jpg"):
                    cards[subdirname].append(filename[0:-4])
    return cards

CONFIG = read_configuration("./d20potz.cfg", "./default.cfg")
CARDS = read_cards(CONFIG.cards_dir)
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

def getPlayerHp(chat_id, player_name):
    player_hp_key = "player_hp_{}_{}".format(chat_id, player_name.lower()).encode('utf-8')
    player_hp = DB.Get(player_hp_key)
    return int(player_hp.decode('utf-8'))

def getPlayerMaxHp(chat_id, player_name):
    player_max_hp_key = "player_max_hp_{}_{}".format(chat_id, player_name.lower()).encode('utf-8')
    player_max_hp = DB.Get(player_max_hp_key)
    return int(player_max_hp.decode('utf-8'))

def setPlayerHp(chat_id, player_name, hp):
    player_hp_key = "player_hp_{}_{}".format(chat_id, player_name.lower()).encode('utf-8')
    DB.Put(player_hp_key, str(hp).encode('utf-8'))

def setPlayerMaxHp(chat_id, player_name, max_hp):
    player_max_hp_key = "player_max_hp_{}_{}".format(chat_id, player_name.lower()).encode('utf-8')
    DB.Put(player_max_hp_key, str(max_hp).encode('utf-8'))

def getSpelling(hero_name):
    hero_name = hero_name.lower()
    for hero, spelling in CONFIG.spelling:
        if hero == hero_name:
            return spelling
    return hero_name

def setPlayerOrder(chat_id, player_list):
    player_list_key = "player_list_{}".format(chat_id).encode('utf-8')
    player_list = ' '.join(player_list)
    DB.Put(player_list_key, player_list.encode('utf-8'))
    setCurrentPlayerId(chat_id, 0)

def setDefaultPlayerOrder(chat_id):
    setPlayerOrder(chat_id, CONFIG.order.lower().split())

def setDefaultHps(chat_id):
    for player_name, hp in CONFIG.hp_defaults:
        setPlayerHp(chat_id, player_name.lower(), hp)
        setPlayerMaxHp(chat_id, player_name.lower(), hp)

def setCardStatusForPlayer(chat_id, player_id, card_id, status: bool):
    card_key = f"card_status_{chat_id}_{player_id}_{card_id}".encode('utf-8')
    logging.info(f"Writting card status for key {card_key}")
    DB.Put(card_key, b'1' if status else b'0')

def getActiveCardsForPlayer(chat_id, player_id):
    key_prefix = f"card_status_{chat_id}_{player_id}_"
    for k, v in DB.RangeIter(
            key_from=key_prefix.encode('utf-8'), 
            key_to=(key_prefix+'\255').encode('utf-8')
        ):
        if v == b'1':
            yield k.decode('utf-8').removeprefix(key_prefix)

###############################################################################################

def error(bot, update, error):
    logger.warning('Update "%s" caused error "%s"' % (update, error))

def ParseArgs():
    parser = optparse.OptionParser()
    return parser.parse_args()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(chat_id=update.effective_chat.id, text="d20potz at your service!")

async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(
            chat_id=update.effective_chat.id, 
            text=f"@{update.message.chat.username} what do you mean "
                 f"\"{update.message.text}\"?")
async def endTurn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    currentPlayer = getPlayerById(update.effective_chat.id, getCurrentPlayerId(update.effective_chat.id))
    nextPlayerId = getNextPlayerId(update.effective_chat.id)
    setCurrentPlayerId(update.effective_chat.id, nextPlayerId)
    nextPlayer = getPlayerById(update.effective_chat.id, nextPlayerId)
    await context.bot.send_message(chat_id=update.effective_chat.id, text="{}'s turn ended. It is now {}'s turn.".format(getSpelling(currentPlayer), getSpelling(nextPlayer)))

async def setPlayerList(update: Update, context: ContextTypes.DEFAULT_TYPE):
    setPlayerOrder(update.effective_chat.id, update.message.text.lower().split()[1:])
    await context.bot.send_message(chat_id=update.effective_chat.id, text="Player list set.")

async def setDefaults(update: Update, context: ContextTypes.DEFAULT_TYPE):
    setDefaultPlayerOrder(update.effective_chat.id)
    setDefaultHps(update.effective_chat.id)
    await context.bot.send_message(chat_id=update.effective_chat.id, text="Defaults set.")

async def currentPlayer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    currentPlayer = getPlayerById(update.effective_chat.id, getCurrentPlayerId(update.effective_chat.id))
    await context.bot.send_message(chat_id=update.effective_chat.id, text="It is {}'s turn.".format(getSpelling(currentPlayer)))

async def roll20(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(chat_id=update.effective_chat.id, text="Rolling... {}".format(
            random.SystemRandom().randint(1,20)))

async def hp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    currentPlayer = getPlayerById(update.effective_chat.id, getCurrentPlayerId(update.effective_chat.id))
    playerName = currentPlayer
    subcommand = "get"
    if len(update.message.text.split()) > 1:
        playerName = update.message.text.split()[1]
    if len(update.message.text.split()) > 2:
        subcommand = update.message.text.split()[2]
    if subcommand == "get":
        try:
            hp = getPlayerHp(update.effective_chat.id, playerName)
            await context.bot.send_message(chat_id=update.effective_chat.id, text="{} has {} HP.".format(getSpelling(playerName), hp))
        except:
            await context.bot.send_message(chat_id=update.effective_chat.id, text="{} does not exist.".format(playerName))
    elif subcommand == "set" or subcommand == "=":
        if len(update.message.text.split()) > 3:
            hp = int(update.message.text.split()[3])
            setPlayerHp(update.effective_chat.id, playerName, hp)
            setPlayerMaxHp(update.effective_chat.id, playerName, hp)
            await context.bot.send_message(chat_id=update.effective_chat.id, text="{}'s HP set to {}.".format(getSpelling(playerName), hp))
        else:
            await context.bot.send_message(chat_id=update.effective_chat.id, text="Usage: /hp <player> = <hp>")
    elif subcommand == "add" or subcommand == "+":
        if len(update.message.text.split()) > 3:
            hp = int(update.message.text.split()[3])
            max_hp = getPlayerMaxHp(update.effective_chat.id, playerName)
            newHp = min(getPlayerHp(update.effective_chat.id, playerName) + hp, max_hp)
            setPlayerHp(update.effective_chat.id, playerName, newHp)
            await context.bot.send_message(chat_id=update.effective_chat.id, text="{}'s HP set to {}.".format(getSpelling(playerName), newHp))
        else:
            await context.bot.send_message(chat_id=update.effective_chat.id, text="Usage: /hp <player> + <hp>")
    elif subcommand == "sub" or subcommand == "-":
        if len(update.message.text.split()) > 3:
            hp = int(update.message.text.split()[3])
            newHp = max(getPlayerHp(update.effective_chat.id, playerName) - hp, 0)
            setPlayerHp(update.effective_chat.id, playerName, newHp)
            await context.bot.send_message(chat_id=update.effective_chat.id, text="{}'s HP set to {}.".format(getSpelling(playerName), newHp))
        else:
            await context.bot.send_message(chat_id=update.effective_chat.id, text="Usage: /hp <player> - <hp>")
    else:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Usage: /hp <player> [get|set|=|add|+|sub|-] <hp>")

async def sendCards(player: str, cards: List[str], chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    media_list = list()
    for playerCard in cards:
        photoFilePath = os.path.join(CONFIG.cards_dir, player.lower(), playerCard + ".jpg")
        media_item = InputMediaPhoto(media=open(photoFilePath, 'rb'))
        media_list.append(media_item)
    await context.bot.send_media_group(chat_id=chat_id, media=media_list)

async def getAllPlayerCards(update: Update, context: ContextTypes.DEFAULT_TYPE):
    currentPlayer = getPlayerById(update.effective_chat.id, getCurrentPlayerId(update.effective_chat.id))
    playerName = currentPlayer
    if len(update.message.text.split()) > 2:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Usage: /getallcards <player>")
    if len(update.message.text.split()) == 2:
        playerName = update.message.text.split()[1]

    playerCards = CARDS[playerName.lower()]
    if len(playerCards) == 0:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="{} has no cards.".format(getSpelling(playerName)))
    else:
        await sendCards(playerName, playerCards, update.effective_chat.id, context)

def get_cards_in_order(player: str):
    return sorted(CARDS[player])

async def processCards(update: Update, context: ContextTypes.DEFAULT_TYPE):
    async def send_to_chat(message: str):
        await context.bot.send_message(chat_id=update.effective_chat.id, 
            text=message)

    command = update.message.text.lower().removeprefix("/cards").lstrip()
    if not command:
        await send_to_chat(f"Usage: /cards (choose|retire|list|names) <card|card_index> [player]")
        return

    player_name = getPlayerById(update.effective_chat.id, getCurrentPlayerId(update.effective_chat.id))
    if command.startswith("list"):
        command = command.removeprefix("list").lstrip()
        player_name = command or player_name

        if active_cards := list(getActiveCardsForPlayer(update.effective_chat.id, player_name)):
            await send_to_chat(f"Listing for {player_name}: {active_cards}")
            await sendCards(player_name, active_cards, update.effective_chat.id, context)
        else:
            await send_to_chat(f"{player_name} does not have active cards")
    elif command.startswith("names"):
        command = command.removeprefix("names").lstrip()
        player_name = command or player_name
        await send_to_chat(f"{player_name}, choose from: " 
                + "\n\t* ".join([ ' ' ] + 
                    [f"{idx}: {name}" for idx, name 
                        in enumerate(get_cards_in_order(player_name))])
            )
    elif command.startswith("choose") or command.startswith("retire"):
        make_active = command.startswith("choose")
        command = command.removeprefix("choose").removeprefix("retire").lstrip()
        if not command:
            await send_to_chat("Usage: /cards (choose|retire) <card|card_index> [player]")
            return

        card, _, maybe_player = command.partition(' ')
        player_name = maybe_player or player_name
        if card.isnumeric():
            card = get_cards_in_order(player_name)[int(card)]
        setCardStatusForPlayer(
                chat_id=update.effective_chat.id, 
                player_id=player_name,
                card_id=card, 
                status=make_active)
        await send_to_chat(f"{player_name} {'activated' if make_active else 'deactivated'} \"{card}\".")
    else:
        await send_to_chat(f"What are you trying to do by sending me \"{command}\"?")

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

    hp_handler = CommandHandler('hp', hp)
    application.add_handler(hp_handler)

    defaults_handler = CommandHandler('defaults', setDefaults)
    application.add_handler(defaults_handler)

    getAllPlayerCards_handler = CommandHandler('getallcards', getAllPlayerCards)
    application.add_handler(getAllPlayerCards_handler)

    cards_handler = CommandHandler('cards', processCards)
    application.add_handler(cards_handler)

    echo_handler = MessageHandler(filters.TEXT & (~filters.COMMAND), echo)
    application.add_handler(echo_handler)
    
    application.run_polling()

if __name__ == "__main__":
    opt, args = ParseArgs()
    d20potzbot()

