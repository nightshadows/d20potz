"""
d20potz specific utilities
"""

import logging
from shared import setup_logging


MAX_DICE = 5


logger = setup_logging(logging.INFO, __name__)


from texts import TEXT_HELP, TEXT_ROLL


def get_client_help_message() -> str:
    """
    Returns the help message for the client
    """
    help_text = f"""
What can this bot do?

1. /add_hero <hero> [stress] [harm] - Add a hero to the list with optional starting stress and harm (default = 0)
2. /add_timer <timer> <start_value> - Add timer with a starting value
3. /help - Show help message
4. /privacy - Show the privacy disclaimer
5. /remove_hero <hero> - Remove a hero from the list
6. /roll - invoke Roll inline keyboard

Using the inline keyboard you can:
- Roll dice
- Add or remove stress or harm from a hero
- Advance or remove timers
""".strip()
    return help_text