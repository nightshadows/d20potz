"""
"""

import boto3
from botocore.exceptions import ClientError
import logging

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)

from telegram.error import BadRequest

from telegram.ext import (
    ContextTypes,
)

from d20potz_state_machine import PotzState, PotzStateMachine
from shared import setup_logging, throttle_telegram
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
class PotzTimer:
    name: str
    value: int

    def __init__(self, name: str, value: int = 0):
        self.name = name
        self.value = value


@dataclass
class BotData:
    user_id: int
    user_name: str
    chat_id: int
    chat_type: str
    params : list[str] = field(default_factory=list)
    last_calls: list[int] = field(default_factory=list)

    def __init__(self, update):
        self.inline_message_id = None
        self.heroes = []
        self.timers = []
        self.last_calls = []
        self.state_machine = None

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
        self.chat_type = update.effective_chat.type
        self.load_state()

    async def throttle(self) -> None:
        # this coroutine modifies the list of last_calls and potentially awaits
        await throttle_telegram(self.last_calls, self.chat_type)

    def set_default_state(self):
        self.state_machine = PotzStateMachine(PotzState.root)

    def load_state(self):
        try:
            response = potztable.get_item(Key={'chat_id': str(self.chat_id)})
            if not 'Item' in response:
                self.set_default_state()
                return

            if 'state' in response['Item']:
                state = PotzState[response['Item']['state']]
                self.state_machine = PotzStateMachine(state)
            else :
                self.state_machine = PotzStateMachine(PotzState.root)

            if 'inline_message_id' in response['Item']:
                self.inline_message_id = response['Item']['inline_message_id']
                if not self.inline_message_id is None:
                    self.inline_message_id = int(self.inline_message_id)

            if 'heroes' in response['Item']:
                self.heroes = [PotzHero(h['name'], h['stress'], h['harm']) for h in response['Item']['heroes']]

            if 'timers' in response['Item']:
                self.timers = [PotzTimer(t['name'], t['value']) for t in response['Item']['timers']]

            if 'last_calls' in response['Item']:
                self.last_calls = [int(lc) for lc in response['Item']['last_calls']]

        except (ClientError, ValueError):
            logger.error("Error loading state", exc_info=True)
            self.set_default_state()

    def save2(self):
        try:
            potztable.put_item(Item={
                'chat_id': str(self.chat_id),
                'state': self.state_machine.get_state().name,
                'inline_message_id': self.inline_message_id,
                'heroes': [{'name': h.name, 'stress': h.stress, 'harm': h.harm} for h in self.heroes],
                'last_calls': self.last_calls,
                'timers': [{'name': t.name, 'value': t.value} for t in self.timers],
            })
        except ClientError:
            logger.error("Error saving state", exc_info=True)

    def add_hero(self, context: ContextTypes.DEFAULT_TYPE) -> str:
        if len(self.params) < 2 or len(self.params) > 4:
            return "Usage: /add_hero <hero> [stress] [harm]"

        hero = self.params[1]
        if '_' in hero:
            return "Hero name cannot contain underscores"

        try:
            stress = int(self.params[2]) if len(self.params) > 2 else 0
            harm = int(self.params[3]) if len(self.params) > 3 else 0
        except ValueError:
            return "Stress and harm should be integers greater than or equal to 0"

        if stress < 0 or harm < 0:
            return "Stress and harm should be greater than or equal to 0"

        if hero in [h.name for h in self.heroes]:
            return "Hero already exists"

        self.heroes.append(PotzHero(hero, stress, harm))
        self.process("root", context)

        return f"Added hero {hero}"

    def remove_hero(self, _context: ContextTypes.DEFAULT_TYPE) -> str:
        if len(self.params) != 2:
            return "Usage: /remove_hero <hero>"

        heroes_before = len(self.heroes)
        hero = self.params[1]
        self.heroes = [h for h in self.heroes if h.name != hero]
        if len(self.heroes) == heroes_before:
            return f"Hero {hero} not found"

        return f"Removed hero {hero}"

    def add_timer(self, _context: ContextTypes.DEFAULT_TYPE) -> str:
        if len(self.params) != 3:
            return "Usage: /add_timer <timer> <start_value>"

        timer = self.params[1]
        if '_' in timer:
            return "Timer name cannot contain underscores"

        try:
            start_value = int(self.params[2])
        except ValueError:
            return "Invalid start value, should be an integer"

        if start_value <= 0:
            return "Start value should be greater than 0"

        if timer in [t.name for t in self.timers]:
            return "Timer already exists"

        self.timers.append(PotzTimer(timer, start_value))

        return f"Added timer {timer} with start value {start_value}"

    async def set_inline_message_id(self, inline_message_id, context: ContextTypes.DEFAULT_TYPE):
        if inline_message_id == self.inline_message_id:
            return

        await self.cleanup_inline_message(context)
        self.inline_message_id = inline_message_id

    async def cleanup_inline_message(self, context: ContextTypes.DEFAULT_TYPE):
        if self.inline_message_id is not None:
            try:
                message_id = self.inline_message_id
                self.inline_message_id = None
                await context.bot.edit_message_reply_markup(
                    chat_id=str(self.chat_id),
                    message_id=int(message_id),
                )
            except BadRequest:
                # this is fine, the message was already deleted
                pass
            except Exception:
                logger.error("Failed to remove the previous inline keyboard", exc_info=True)

    def get_default_header(self):
        return f"D20 potz: {self.state_machine.get_state().name}"

    def transition(self, to_state):
        if self.state_machine.can_transition(to_state):
            self.state_machine.transition(to_state)
        else:
            logger.error("Cannot transition from %s to %s", self.state_machine.get_state(), to_state)
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

    async def process_hero(self, callback: str, _context: ContextTypes.DEFAULT_TYPE) -> str:
        callback_parts = callback.split("_")
        if len(callback_parts) != 3:
            if len(callback_parts) == 2:
                return f"Press +/- to modify {callback_parts[1]}'s {callback_parts[0]}"
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

        return self.get_default_header()

    async def process_timer(self, callback: str, _context: ContextTypes.DEFAULT_TYPE) -> str:
        callback_parts = callback.split("_")
        if len(callback_parts) != 3:
            if len(callback_parts) == 2:
                return f"Press - to decrease timer {callback_parts[1]}"
            return "Invalid timer callback"

        timer_name = callback_parts[2]
        timer_op = callback_parts[1]

        if timer_op not in ["minus", "remove"]:
            return "Invalid operation"

        timer = next((t for t in self.timers if t.name == timer_name), None)
        if timer is None:
            return "Timer not found"

        if timer_op == "remove":
            self.timers = [t for t in self.timers if t.name != timer_name]
            return f"Removed timer {timer_name}"

        timer.value -= 1
        if timer.value == 0:
            return f"Timer {timer_name} expired"

        return f"Timer {timer_name} decreased to {timer.value}"

    async def process(self, callback: str, context: ContextTypes.DEFAULT_TYPE) -> str:
        try:
            await self.cleanup_inline_message(context)

            if callback in [item.value for item in PotzState]:
                return self.transition(PotzState(callback))

            state = self.state_machine.get_state()
            if state == PotzState.root:
                pass
            elif state in (PotzState.stress, PotzState.harm):
                return await self.process_hero(callback, context)
            elif state == PotzState.timer:
                return await self.process_timer(callback, context)
            elif state == PotzState.roll:
                logger.info("Roll callback: %s", callback)
                if not callback.startswith("roll"):
                    pass
                else:
                    dice_count = int(callback[4])
                    logger.info("Rolling %s dice", dice_count)
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

    def build_timer_keyboard(self):
        keyboard = []
        for timer in self.timers:
            line = []
            line.append(InlineKeyboardButton(f"{timer.name}", callback_data=f"timer_{timer.name}"))
            if timer.value > 0:
                line.append(InlineKeyboardButton(f"{timer.value} -> {timer.value - 1}", callback_data=f"timer_minus_{timer.name}"))
            line.append(InlineKeyboardButton("Remove", callback_data=f"timer_remove_{timer.name}"))
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
            keyboard = self.build_timer_keyboard()
        elif state == PotzState.roll:
            keyboard = [
                [InlineKeyboardButton("1d6", callback_data="roll1"), InlineKeyboardButton("2d6", callback_data="roll2"), InlineKeyboardButton("3d6", callback_data="roll3")],
                [InlineKeyboardButton("4d6", callback_data="roll4"), InlineKeyboardButton("5d6", callback_data="roll5"), InlineKeyboardButton("6d6", callback_data="roll6")],
                [InlineKeyboardButton("Back", callback_data=PotzState.root.name)],
            ]

        return InlineKeyboardMarkup(keyboard)

