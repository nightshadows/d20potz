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

1. {TEXT_HELP} - Show this help message
2. {TEXT_ROLL} [num_dice] - Roll a few d6 dice (between 1 and {MAX_DICE}, default is 1)
""".strip()
    return help_text