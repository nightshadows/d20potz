"""
"""

import boto3
from botocore.exceptions import ClientError
import logging

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)

from telegram.ext import (
    ContextTypes,
)

from d20potz_state_machine import PotzState, PotzStateMachine
from shared import setup_logging
from dataclasses import dataclass, field


logger = setup_logging(logging.INFO, __name__)
POTZ_TABLE = "potz_manager"
dynamodb = boto3.resource('dynamodb')
potztable = dynamodb.Table(POTZ_TABLE)


@dataclass
class PotzHero:
    name: str
    stress: int
    harm: int

    def __init__(self, name: str, stress: int = 0, harm: int = 0):
        self.name = name
        self.stress = stress
        self.harm = harm


@dataclass
class BotData:
    user_id: int
    user_name: str
    chat_id: int
    params : list[str] = field(default_factory=list)


    def __init__(self, update):
        if not (message := update.message):
            message = update.edited_message
        if message:
            self.user_id = message.from_user.id
            self.user_name = message.from_user.username
            self.params = message.text.split() if message.text else []
        elif update.callback_query:
            self.user_id = update.callback_query.from_user.id
            self.user_name = update.callback_query.from_user.username
            self.params = update.callback_query.data.split() if update.callback_query.data else []

        self.chat_id = update.effective_chat.id
        self.sync()
        logger.info(f"BotData: {self}")

    def sync(self):
        self.load_state()
        self.load_inline_message_id()
        self.load_heroes()

    def load_state(self):
        try:
            response = potztable.get_item(Key={'chat_id': str(self.chat_id)})
            if 'Item' in response and 'state' in response['Item']:
                state = PotzState[response['Item']['state']]
            else:
                state = PotzState.root
            self.state_machine = PotzStateMachine(state)
        except (ClientError, ValueError):
            logger.error("Error loading state", exc_info=True)
            self.state_machine = PotzStateMachine(PotzState.root)

    def load_inline_message_id(self):
        try:
            response = potztable.get_item(Key={'chat_id': str(self.chat_id)})
            if 'Item' in response and 'inline_message_id' in response['Item']:
                self.inline_message_id = response['Item'].get('inline_message_id')
                if not self.inline_message_id is None:
                    self.inline_message_id = int(self.inline_message_id)
            else:
                self.inline_message_id = None
        except ClientError:
            logger.error("Error loading inline message id", exc_info=True)
            self.inline_message_id = None

    def load_heroes(self):
        try:
            response = potztable.get_item(Key={'chat_id': str(self.chat_id)})
            if 'Item' in response and 'heroes' in response['Item']:
                self.heroes = [PotzHero(h['name'], h['stress'], h['harm']) for h in response['Item']['heroes']]
            else:
                self.heroes = []
        except ClientError:
            logger.error("Error loading heroes", exc_info=True)
            self.heroes = []

    def save(self):
        try:
            potztable.put_item(Item={
                'chat_id': str(self.chat_id),
                'state': self.state_machine.get_state().name,
                'inline_message_id': self.inline_message_id,
                'heroes': [{'name': h.name, 'stress': h.stress, 'harm': h.harm} for h in self.heroes],
            })
        except ClientError:
            logger.error("Error saving state", exc_info=True)

    def add_hero(self, context: ContextTypes.DEFAULT_TYPE) -> str:
        if len(self.params) < 2 or len(self.params) > 4:
            return "Usage: /add_hero <hero> [stress] [harm]"

        hero = self.params[1]
        stress = int(self.params[2]) if len(self.params) > 2 else 0
        harm = int(self.params[3]) if len(self.params) > 3 else 0

        if hero in [h.name for h in self.heroes]:
            return "Hero already exists"

        self.heroes.append(PotzHero(hero, stress, harm))
        self.save()

        self.process("root", context)

        return f"Added hero {hero}"

    def remove_hero(self, context: ContextTypes.DEFAULT_TYPE) -> str:
        if len(self.params) != 2:
            return "Usage: /remove_hero <hero>"

        heroes_before = len(self.heroes)
        hero = self.params[1]
        self.heroes = [h for h in self.heroes if h.name != hero]
        if len(self.heroes) == heroes_before:
            return f"Hero {hero} not found"

        self.save()
        return f"Removed hero {hero}"

    async def set_inline_message_id(self, inline_message_id, context: ContextTypes.DEFAULT_TYPE):
        if inline_message_id == self.inline_message_id:
            return

        await self.cleanup_inline_message(context)
        self.inline_message_id = inline_message_id
        self.save()

    async def cleanup_inline_message(self, context: ContextTypes.DEFAULT_TYPE):
        logger.info("Cleaning up inline message %s for chat %s", self.inline_message_id, self.chat_id)
        if self.inline_message_id is not None:
            try:
                message_id = self.inline_message_id
                self.inline_message_id = None
                await context.bot.edit_message_reply_markup(
                    chat_id=str(self.chat_id),
                    message_id=int(message_id),
                )
            except Exception:
                logger.error("Failed to remove the previous inline keyboard", exc_info=True)

    def get_default_header(self):
        return f"D20 potz: {self.state_machine.get_state().name}"

    def transition(self, to_state):
        if self.state_machine.can_transition(to_state):
            self.state_machine.transition(to_state)
            self.save()
        else:
            logger.error(f"Cannot transition from {self.state_machine.get_state()} to {to_state}")
        return self.get_default_header()

    async def process_roll(self, dice_count: int, context: ContextTypes.DEFAULT_TYPE) -> str:
        dice_results = []
        for _ in range(dice_count):
            message = await context.bot.send_dice(chat_id=self.chat_id)
            dice_results.append(message.dice.value)

        dice_results_str = ", ".join(map(str, dice_results))
        text = f"Rolling {dice_count} {'die' if dice_count == 1 else 'dice'}... {dice_results_str}"
        await context.bot.send_message(
            chat_id=self.chat_id,
            text=text,
        )

        return self.transition(PotzState.root)

    async def process_hero(self, callback: str, context: ContextTypes.DEFAULT_TYPE) -> str:
        callback_parts = callback.split("_")
        if len(callback_parts) != 3:
            return "Invalid hero callback"

        hero_name = callback_parts[2]
        hero_field = callback_parts[0]
        hero_op = callback_parts[1]

        if hero_field not in ["stress", "harm"]:
            return "Invalid hero field"

        if hero_op not in ["plus", "minus"]:
            return "Invalid operation"

        hero = next((h for h in self.heroes if h.name == hero_name), None)
        if hero is None:
            return "Hero not found"

        value = getattr(hero, hero_field)
        if hero_op == "plus":
            value += 1
        else:
            value -= 1

        setattr(hero, hero_field, value)
        self.save()

        return self.get_default_header()

    async def process(self, callback: str, context: ContextTypes.DEFAULT_TYPE) -> str:
        try:
            logger.info(f"Processing callback {callback}")

            await self.cleanup_inline_message(context)

            if callback in [item.value for item in PotzState]:
                return self.transition(PotzState(callback))

            state = self.state_machine.get_state()
            if state == PotzState.root:
                pass
            elif state in (PotzState.stress, PotzState.harm):
                return await self.process_hero(callback, context)
            elif state == PotzState.timer:
                pass
            elif state == PotzState.roll:
                logger.info(f"Roll callback: {callback}")
                if not callback.startswith("roll"):
                    pass
                else:
                    dice_count = int(callback[4])
                    logger.info(f"Rolling {dice_count} dice")
                    return await self.process_roll(dice_count, context)
        except Exception:
            logger.error("Error processing callback", exc_info=True)

        return self.get_default_header()

    def build_hero_keyboard(self, state: str):
        keyboard = []
        for hero in self.heroes:
            line = []
            value = getattr(hero, state)
            line.append(InlineKeyboardButton(f"{hero.name}: {value}", callback_data=f"{state}_{hero.name}"))
            line.append(InlineKeyboardButton("+", callback_data=f"{state}_plus_{hero.name}"))
            if value > 0:
                line.append(InlineKeyboardButton("-", callback_data=f"{state}_minus_{hero.name}"))
            keyboard.append(line)
        keyboard.append([InlineKeyboardButton("Back", callback_data=PotzState.root.name)])
        return keyboard

    def get_inline_keyboard(self):
        state = self.state_machine.get_state()
        keyboard = []

        if state == PotzState.root:
            keyboard = [
                [InlineKeyboardButton("Roll", callback_data=PotzState.roll.name), InlineKeyboardButton("Timer", callback_data=PotzState.timer.name)],
                [InlineKeyboardButton("Harm", callback_data=PotzState.harm.name), InlineKeyboardButton("Stress", callback_data=PotzState.stress.name)],
            ]
        elif state == PotzState.stress:
            keyboard = self.build_hero_keyboard("stress")
        elif state == PotzState.harm:
            keyboard = self.build_hero_keyboard("harm")
        elif state == PotzState.timer:
            keyboard = [[InlineKeyboardButton("Back", callback_data=PotzState.root.name)]]
        elif state == PotzState.roll:
            keyboard = [
                [InlineKeyboardButton("1d6", callback_data="roll1"), InlineKeyboardButton("2d6", callback_data="roll2"), InlineKeyboardButton("3d6", callback_data="roll3")],
                [InlineKeyboardButton("4d6", callback_data="roll4"), InlineKeyboardButton("5d6", callback_data="roll5"), InlineKeyboardButton("6d6", callback_data="roll6")],
                [InlineKeyboardButton("Back", callback_data=PotzState.root.name)],
            ]

        return InlineKeyboardMarkup(keyboard)

