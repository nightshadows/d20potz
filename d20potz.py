#! /usr/bin/env python3
# -*- coding: utf-8 -*-

import collections
import leveldb
import logging
import optparse
import os

from typing import List

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
)

from potz import roll20

D20PotzBotConfiguration = collections.namedtuple(
    "D20PotzBotConfiguration",
    "db_location token cards_dir spelling order hp_defaults xp_default",
)


def read_configuration(secret_config, default_config):
    from configparser import ConfigParser

    cp = ConfigParser()
    if secret_config in cp.read([secret_config, default_config]):
        db_location = cp.get("bot", "db_dir")
        token = cp.get("bot", "telegram_token")
        cards_dir = cp.get("bot", "cards_dir", fallback="./cards")
        spelling = dict(cp.items("spelling"))
        order = cp.get("general", "player_list", fallback="")
        xp_default = cp.get("general", "xp", fallback="0")
        hp_defaults = cp.items("hp")
        return D20PotzBotConfiguration(
            db_location, token, cards_dir, spelling, order, hp_defaults, xp_default
        )


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
ITEMS = CARDS["items"]
DB = leveldb.LevelDB(CONFIG.db_location)

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)

logger = logging.getLogger(__name__)


def ParseArgs():
    parser = optparse.OptionParser()
    return parser.parse_args()


###############################################################################################


def get_current_player_id(chat_id):
    current_player_id_key = "current_player_{}".format(chat_id).encode("utf-8")
    current_player_id = DB.Get(current_player_id_key)
    return int(current_player_id.decode("utf-8"))


def get_player_by_id(chat_id, player_id):
    player_list_key = "player_list_{}".format(chat_id).encode("utf-8")
    player_list = DB.Get(player_list_key).decode("utf-8").split()
    return player_list[player_id]


def get_next_player_id(chat_id):
    player_list_key = "player_list_{}".format(chat_id).encode("utf-8")
    player_list = DB.Get(player_list_key).decode("utf-8").split()
    current_player_id_key = "current_player_{}".format(chat_id).encode("utf-8")
    current_player_id = int(DB.Get(current_player_id_key).decode("utf-8"))
    next_player_id = (int(current_player_id) + 1) % len(player_list)
    return next_player_id


def set_current_player_id(chat_id, player_id: int):
    current_player_id_key = "current_player_{}".format(chat_id).encode("utf-8")
    DB.Put(current_player_id_key, str(player_id).encode("utf-8"))


def get_player_hp(chat_id, player_name):
    player_hp_key = "player_hp_{}_{}".format(chat_id, player_name.lower()).encode(
        "utf-8"
    )
    player_hp = DB.Get(player_hp_key)
    return int(player_hp.decode("utf-8"))


def get_xp(chat_id):
    xp_key = "xp_{}".format(chat_id).encode("utf-8")
    try:
        xp = DB.Get(xp_key)
    except:
        xp = CONFIG.xp_default
        set_xp(chat_id, int(xp))
    return int(xp.decode("utf-8"))


def get_player_max_hp(chat_id, player_name):
    player_max_hp_key = "player_max_hp_{}_{}".format(
        chat_id, player_name.lower()
    ).encode("utf-8")
    player_max_hp = DB.Get(player_max_hp_key)
    return int(player_max_hp.decode("utf-8"))


def set_player_hp(chat_id, player_name, hp):
    player_hp_key = "player_hp_{}_{}".format(chat_id, player_name.lower()).encode(
        "utf-8"
    )
    DB.Put(player_hp_key, str(hp).encode("utf-8"))


def set_xp(chat_id, xp):
    xp_key = "xp_{}".format(chat_id).encode("utf-8")
    DB.Put(xp_key, str(xp).encode("utf-8"))


def set_player_max_hp(chat_id, player_name, max_hp):
    player_max_hp_key = "player_max_hp_{}_{}".format(
        chat_id, player_name.lower()
    ).encode("utf-8")
    DB.Put(player_max_hp_key, str(max_hp).encode("utf-8"))


def spell_hero_name(hero_name):
    return CONFIG.spelling.get(hero_name.lower(), hero_name)


def set_player_order(chat_id, player_list):
    player_list_key = "player_list_{}".format(chat_id).encode("utf-8")
    player_list = " ".join(player_list)
    DB.Put(player_list_key, player_list.encode("utf-8"))
    set_current_player_id(chat_id, 0)


def set_player_card_status(chat_id, player_id, card_id, flipped: bool):
    card_key = f"card_status_{chat_id}_{player_id}_{card_id}".encode("utf-8")
    logging.info(f"Writing card status for key {card_key}")
    DB.Put(card_key, b"1" if flipped else b"0")


def remove_player_card_status(chat_id, player_id, card_id):
    card_key = f"card_status_{chat_id}_{player_id}_{card_id}".encode("utf-8")
    DB.Delete(card_key)


def get_player_cards(chat_id, player_id, flipped: bool):
    key_prefix = f"card_status_{chat_id}_{player_id}_"
    for k, v in DB.RangeIter(
        key_from=key_prefix.encode("utf-8"),
        key_to=(key_prefix + "\255").encode("utf-8"),
    ):
        if flipped is None or (flipped and v == b"1") or (not flipped and v == b"0"):
            yield k.decode("utf-8").removeprefix(key_prefix)


async def send_cards(
    player: str, cards: List[str], chat_id: int, context: ContextTypes.DEFAULT_TYPE
):
    media_list = list()
    for card in cards:
        photo_file_path = os.path.join(CONFIG.cards_dir, player.lower(), card + ".jpg")
        media_item = InputMediaPhoto(media=open(photo_file_path, "rb"))
        media_list.append(media_item)
    if media_list:
        await context.bot.send_media_group(chat_id=chat_id, media=media_list)


async def check_player_name(context: ContextTypes.DEFAULT_TYPE, chat_id, player_name):
    player_list = CONFIG.order.lower().split()
    if player_name not in player_list:
        await context.bot.send_message(
            chat_id=chat_id,
            text="{} is not one of {}".format(
                spell_hero_name(player_name), player_list
            ),
        )
        return False
    return True


def set_claim_status(chat_id, player_name, user_id, claim: bool):
    claim_key = f"player_claim_{chat_id}_{player_name}".encode("utf-8")
    logging.info(f"Writing claim status for key {claim_key}")
    if claim:
        DB.Put(claim_key, str(user_id).encode("utf-8"))
    else:
        DB.Delete(claim_key)


def get_player_by_user(chat_id, user_id):
    player_list = CONFIG.order.lower().split()

    for player_name in player_list:
        claim_key = f"player_claim_{chat_id}_{player_name}".encode("utf-8")
        claimant = DB.Get(claim_key, default=None)
        if claimant != None and claimant.decode() == str(user_id):
            return player_name

    return None


def is_player_claimed(chat_id, player_name):
    claim_key = f"player_claim_{chat_id}_{player_name}".encode("utf-8")
    claimed_user_id = DB.Get(claim_key, default=None)
    return claimed_user_id != None


def is_player_claimed_by_user(chat_id, player_name, user_id):
    claim_key = f"player_claim_{chat_id}_{player_name}".encode("utf-8")
    claimed_user_id = DB.Get(claim_key, default=None)
    return claimed_user_id != None and claimed_user_id.decode() == str(user_id)


def get_player_items(chat_id, player_id):
    items_key = f"player_items_{chat_id}_{player_id}".encode("utf-8")
    items = DB.Get(items_key, default="".encode("utf-8"))
    return items.decode("utf-8").split()


def add_player_item(chat_id, player_id, item_id) -> bool:
    item_id = item_id.lower()
    items_key = f"player_items_{chat_id}_{player_id}".encode("utf-8")
    items = DB.Get(items_key, default="".encode("utf-8"))
    items = items.decode("utf-8").split()
    if item_id in items:
        return False

    items.append(item_id)
    DB.Put(items_key, " ".join(items).encode("utf-8"))
    return True


def remove_player_item(chat_id, player_id, item_id) -> bool:
    item_id = item_id.lower()
    items_key = f"player_items_{chat_id}_{player_id}".encode("utf-8")
    items = DB.Get(items_key, default="".encode("utf-8"))
    items = items.decode("utf-8").split()
    if item_id not in items:
        return False

    items.remove(item_id)
    DB.Put(items_key, " ".join(items).encode("utf-8"))
    return True


###############################################################################################


async def turn_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    params = update.message.text.split()
    chat_id = update.effective_chat.id
    sub_command = "get" if len(params) == 1 else params[1]
    if sub_command == "get":
        current_player = get_player_by_id(
            update.effective_chat.id, get_current_player_id(update.effective_chat.id)
        )
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="It is {}'s turn.".format(spell_hero_name(current_player)),
        )
    elif sub_command == "set":
        players = update.message.text.lower().split()[2:]
        full_player_list = CONFIG.order.lower().split()
        players_filtered = [c for c in players if c in full_player_list]
        set_player_order(update.effective_chat.id, players)
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Player list is set to {}.".format(players_filtered),
        )
    elif sub_command == "next":
        current_player = get_player_by_id(
            update.effective_chat.id, get_current_player_id(update.effective_chat.id)
        )
        next_player_id = get_next_player_id(update.effective_chat.id)
        set_current_player_id(update.effective_chat.id, next_player_id)
        next_player = get_player_by_id(update.effective_chat.id, next_player_id)
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="{}'s turn ended. It is now {}'s turn.".format(
                spell_hero_name(current_player), spell_hero_name(next_player)
            ),
        )
    else:
        await context.bot.send_message(
            chat_id=chat_id,
            text="{} is not one of {}".format(sub_command, ["get", "set", "next"]),
        )


async def hp_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id

    player_name = get_player_by_user(chat_id, update.message.from_user.id)
    params = update.message.text.split()

    if len(params) > 1:
        player_param = params[1].lower()
        player_list = CONFIG.order.lower().split()
        if player_param in player_list:
            player_name = player_param
            del params[1]

    sub_command = "get" if len(params) == 1 else params[1]
    if sub_command == "get":
        try:
            hp = get_player_hp(update.effective_chat.id, player_name)
        except:
            await context.bot.send_message(
                chat_id=chat_id,
                text="{} does not have hp set.".format(spell_hero_name(player_name)),
            )
            return
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="{} has {} HP.".format(
                spell_hero_name(spell_hero_name(player_name)), hp
            ),
        )
    elif sub_command == "set" or sub_command == "=":
        hp = int(params[2])
        set_player_hp(update.effective_chat.id, player_name, hp)
        set_player_max_hp(update.effective_chat.id, player_name, hp)
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="{}'s HP set to {}.".format(spell_hero_name(player_name), hp),
        )

    elif sub_command == "add" or sub_command == "+":
        hp = int(params[2])
        try:
            max_hp = get_player_max_hp(update.effective_chat.id, player_name)
        except:
            await context.bot.send_message(
                chat_id=chat_id,
                text="{} does not have hp set.".format(spell_hero_name(player_name)),
            )
            return
        new_hp = min(get_player_hp(update.effective_chat.id, player_name) + hp, max_hp)
        set_player_hp(update.effective_chat.id, player_name, new_hp)
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="{}'s HP set to {}.".format(spell_hero_name(player_name), new_hp),
        )
    elif sub_command == "sub" or sub_command == "-":
        hp = int(params[2])
        try:
            new_hp = max(get_player_hp(update.effective_chat.id, player_name) - hp, 0)
        except:
            await context.bot.send_message(
                chat_id=chat_id,
                text="{} does not have hp set.".format(spell_hero_name(player_name)),
            )
            return
        set_player_hp(update.effective_chat.id, player_name, new_hp)
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="{}'s HP set to {}.".format(spell_hero_name(player_name), new_hp),
        )

    else:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Usage: /hp (player) [+|-] <hp>",
        )


async def xp_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    params = update.message.text.split()

    sub_command = "get" if len(params) == 1 else params[1]
    if sub_command == "get":
        try:
            xp = get_xp(chat_id)
        except:
            await context.bot.send_message(
                chat_id,
                text="xp not set",
            )
            return
        await context.bot.send_message(
            chat_id,
            text="Party has {} XP".format(xp),
        )
    elif sub_command == "set" or sub_command == "=":
        xp = int(params[2])
        set_xp(chat_id, xp)
        await context.bot.send_message(
            chat_id,
            text="Party's XP set to {}".format(xp),
        )

    elif sub_command == "add" or sub_command == "+":
        xp_to_add = int(params[2])
        try:
            xp = get_xp(chat_id)
        except:
            await context.bot.send_message(
                chat_id,
                text="Party's XP set to {}".format(xp),
            )
            return
        new_xp = xp + xp_to_add
        set_xp(chat_id, new_xp)
        await context.bot.send_message(
            chat_id,
            text="Party's XP set to {}".format(new_xp),
        )
    elif sub_command == "sub" or sub_command == "-":
        xp_to_sub = int(params[2])
        try:
            xp = get_xp(chat_id)
        except:
            await context.bot.send_message(
                chat_id,
                text="Party's XP set to {}".format(xp),
            )
            return
        new_xp = xp - xp_to_sub
        set_xp(chat_id, new_xp)
        await context.bot.send_message(
            chat_id,
            text="Party's XP set to {}".format(new_xp),
        )

    else:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Usage: /xp [+|-] <xp>",
        )


async def cards_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    params = update.message.text.split()
    chat_id = update.effective_chat.id

    player_name = get_player_by_user(chat_id, update.message.from_user.id)

    if len(params) > 1:
        player_param = params[1].lower()
        player_list = CONFIG.order.lower().split()
        if player_param in player_list:
            player_name = player_param
            del params[1]

    sub_command = "hand" if len(params) == 1 else params[1]
    if sub_command == "all":
        player_cards = CARDS[player_name]
        if not player_cards:
            await context.bot.send_message(
                chat_id=chat_id,
                text="{} has no cards.".format(spell_hero_name(player_name)),
            )
        else:
            await send_cards(player_name, player_cards, chat_id, context)
        return
    elif sub_command == "show":
        if len(params) < 2:
            await context.bot.send_message(
                chat_id=chat_id, text="Usage: /cards show <card name> (player)"
            )
            return

        card_name = params[2]
        player_cards = [c for c in CARDS[player_name] if card_name in c]
        if len(player_cards) == 0:
            await context.bot.send_message(
                chat_id=chat_id,
                text="Cound not find {} in {}".format(card_name, CARDS[player_name]),
            )
        else:
            await send_cards(player_name, player_cards, chat_id, context)
        return
    elif sub_command == "draw":
        if len(params) < 2:
            await context.bot.send_message(
                chat_id=chat_id, text="Usage: /cards draw <card name> (player)"
            )
            return

        card_name = params[2]
        player_cards = player_cards = [c for c in CARDS[player_name] if card_name in c]
        if len(player_cards) == 0:
            await context.bot.send_message(
                chat_id=chat_id,
                text="Could not find {} in {}".format(card_name, CARDS[player_name]),
            )
        set_player_card_status(chat_id, player_name, player_cards[0], flipped=False)
        await context.bot.send_message(
            chat_id=chat_id,
            text="{} drew {}".format(spell_hero_name(player_name), player_cards[0]),
        )
        return
    elif sub_command == "discard":
        if len(params) < 2:
            await context.bot.send_message(
                chat_id=chat_id, text="Usage: /cards flip <card name> (player)"
            )
            return

        card_name = params[2]
        all_cards = list(
            get_player_cards(update.effective_chat.id, player_name, flipped=None)
        )
        discarded_cards = [c for c in all_cards if card_name in c]

        list(filter(lambda card: card.find(card_name) != -1, all_cards))
        if len(discarded_cards) != 1:
            await context.bot.send_message(
                chat_id=chat_id,
                text="Could not find {} in {}'s hand {}".format(
                    card_name, spell_hero_name(player_name), all_cards
                ),
            )
            return
        remove_player_card_status(chat_id, player_name, discarded_cards[0])
        await context.bot.send_message(
            chat_id=chat_id,
            text="{} discarded {}".format(
                spell_hero_name(player_name), discarded_cards[0]
            ),
        )
        return
    elif sub_command == "hand":
        await send_cards(
            player_name,
            cards=[
                c
                for c in get_player_cards(
                    update.effective_chat.id, player_name, flipped=False
                )
                if c in CARDS[player_name]
            ],
            chat_id=chat_id,
            context=context,
        )
        if flipped_cards := list(
            get_player_cards(update.effective_chat.id, player_name, flipped=True)
        ):
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"{spell_hero_name(player_name)}'s flipped cards {flipped_cards}",
            )
        return
    elif sub_command == "flip":
        if len(params) < 2:
            await context.bot.send_message(
                chat_id=chat_id, text="Usage: /cards (player) flip <card name>"
            )
            return

        card_name = params[2]
        not_flipped_cards = [
            c
            for c in get_player_cards(
                update.effective_chat.id, player_name, flipped=False
            )
            if card_name in c
        ]
        flipped_cards = [
            c
            for c in get_player_cards(
                update.effective_chat.id, player_name, flipped=True
            )
            if card_name in c
        ]
        if len(not_flipped_cards) == 0 and len(flipped_cards) == 0:
            await context.bot.send_message(
                chat_id=chat_id,
                text="Could not find {} in {}'s hand {}".format(
                    card_name,
                    spell_hero_name(player_name),
                    list(
                        get_player_cards(
                            update.effective_chat.id, player_name, flipped=None
                        )
                    ),
                ),
            )
            return

        if len(not_flipped_cards) > 0:
            set_player_card_status(
                chat_id, player_name, not_flipped_cards[0], flipped=True
            )
            await context.bot.send_message(
                chat_id=chat_id,
                text="{} flipped {}".format(
                    spell_hero_name(player_name), not_flipped_cards[0]
                ),
            )
        else:
            set_player_card_status(
                chat_id, player_name, flipped_cards[0], flipped=False
            )
            await context.bot.send_message(
                chat_id=chat_id,
                text="{} unflipped {}".format(
                    spell_hero_name(player_name), flipped_cards[0]
                ),
            )
        return
    else:
        await context.bot.send_message(
            chat_id=chat_id,
            text="{} is not one of {}".format(
                sub_command, ["all", "show", "draw", "discard", "hand", "flip"]
            ),
        )
        return


async def items_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    params = update.message.text.split()
    chat_id = update.effective_chat.id

    player_name = get_player_by_user(chat_id, update.message.from_user.id)

    if len(params) > 1:
        player_param = params[1].lower()
        player_list = CONFIG.order.lower().split()
        if player_param in player_list:
            player_name = player_param
            del params[1]

    sub_command = "hand" if len(params) == 1 else params[1]
    if sub_command == "hand":
        await send_cards(
            "items",
            get_player_items(update.effective_chat.id, player_name),
            chat_id=chat_id,
            context=context,
        )
        return
    elif sub_command == "add":
        if len(params) < 2:
            await context.bot.send_message(
                chat_id=chat_id, text="Usage: /items add <item name> (player)"
            )
            return

        item_name = params[2]
        item_cards = [c for c in ITEMS if item_name in c]
        if len(item_cards) == 0:
            await context.bot.send_message(
                chat_id=chat_id,
                text="Could not find {} in {}".format(item_name, ITEMS),
            )
            return
        added = add_player_item(chat_id, player_name, item_cards[0])
        if added:
            await context.bot.send_message(
                chat_id=chat_id,
                text="{} added {}".format(spell_hero_name(player_name), item_cards[0]),
            )
        else:
            await context.bot.send_message(
                chat_id=chat_id,
                text="{} already has {}".format(
                    spell_hero_name(player_name), item_cards[0]
                ),
            )
        return
    elif sub_command == "discard":
        if len(params) < 2:
            await context.bot.send_message(
                chat_id=chat_id, text="Usage: /items discard <item name> (player)"
            )
            return

        item_name = params[2]
        item_cards = [c for c in ITEMS if item_name in c]
        if len(item_cards) == 0:
            await context.bot.send_message(
                chat_id=chat_id,
                text="Could not find {} in {}".format(item_name, ITEMS),
            )
            return
        removed = remove_player_item(chat_id, player_name, item_cards[0])
        if removed:
            await context.bot.send_message(
                chat_id=chat_id,
                text="{} removed {}".format(
                    spell_hero_name(player_name), item_cards[0]
                ),
            )
        else:
            await context.bot.send_message(
                chat_id=chat_id,
                text="{} did not have {}".format(
                    spell_hero_name(player_name), item_cards[0]
                ),
            )
        return
    else:
        await context.bot.send_message(
            chat_id=chat_id,
            text="{} is not one of {}".format(sub_command, ["hand", "add", "discard"]),
        )
        return


async def claim_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    params = update.message.text.split()
    chat_id = update.effective_chat.id
    user_id = update.message.from_user.id

    if len(params) < 2:
        await context.bot.send_message(chat_id=chat_id, text="Usage: /claim <player>")
        return

    player_name = params[1].lower()
    if not await check_player_name(context, chat_id, player_name):
        return

    if is_player_claimed(chat_id, player_name):
        if is_player_claimed_by_user(chat_id, player_name, user_id):
            await context.bot.send_message(
                chat_id=chat_id, text="You've already claimed {}".format(player_name)
            )
            return
        else:
            await context.bot.send_message(
                chat_id=chat_id, text="{} claim cleared".format(player_name)
            )
            set_claim_status(chat_id, player_name, None, False)

    current_claim = get_player_by_user(chat_id, user_id)
    if current_claim != None:
        await context.bot.send_message(
            chat_id=chat_id, text="{} unclaimed".format(current_claim)
        )
        set_claim_status(chat_id, current_claim, user_id, False)

    await context.bot.send_message(
        chat_id=chat_id, text="{} claimed".format(player_name)
    )
    set_claim_status(chat_id, player_name, user_id, True)


async def help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="list of commands \n"
        + "/roll20 - roll a d20 \n"
        + "/cards (player) - list cards in player hand \n"
        + "/cards (player) all <player> - show all player cards with images \n"
        + "/cards (player) show <card name> - show image of a single card \n"
        + "/cards (player) draw <card name> - add card to player hand \n"
        + "/cards (player) discard <card name> - remove card from player hand \n"
        + "/cards (player) flip <card name> - turn card from player hand \n"
        + "/hp <player> - show player hit points \n"
        + "/hp (player) = X - set player hit points to X \n"
        + "/hp (player) + X - increase player hit points by X \n"
        + "/hp (player) - X - decrease player hit points by X \n"
        + "/xp - show current team xp \n"
        + "/xp = value - set xp \n"
        + "/xp + value - increase xp \n"
        + "/xp - value - decrease xp \n"
        + "/turn - show current turn \n"
        + "/turn set <player1>,<player2>... - set order of players \n"
        + "/turn next - advance to next player \n"
        + "/claim <player> - claim player to your account \n",
    )


def d20potzbot():
    application = ApplicationBuilder().token(CONFIG.token).build()

    help_handler = CommandHandler("help", help)
    application.add_handler(help_handler)

    roll20_handler = CommandHandler("roll20", roll20.roll20)
    application.add_handler(roll20_handler)

    turn_handler = CommandHandler("turn", turn_command)
    application.add_handler(turn_handler)

    hp_handler = CommandHandler("hp", hp_command)
    application.add_handler(hp_handler)

    xp_handler = CommandHandler("xp", xp_command)
    application.add_handler(xp_handler)

    cards_handler = CommandHandler("cards", cards_command)
    application.add_handler(cards_handler)

    items_handler = CommandHandler("items", items_command)
    application.add_handler(items_handler)

    claim_handler = CommandHandler("claim", claim_command)
    application.add_handler(claim_handler)

    async def error(update, context):
        import traceback
        import html
        import json

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

        await context.bot.send_message(
            chat_id=update.effective_chat.id, text=message, parse_mode=ParseMode.HTML
        )

    application.add_error_handler(error)

    application.run_polling()


if __name__ == "__main__":
    opt, args = ParseArgs()
    d20potzbot()
