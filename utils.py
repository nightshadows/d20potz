"""
d20potz specific utilities
"""

import logging
from shared import setup_logging


logger = setup_logging(logging.INFO, __name__)


from texts import TEXT_HELP, TEXT_ROLL


def get_client_help_message() -> str:
    """
    Returns the help message for the client
    """
    help_text = "What can this bot do?\n\n"
    help_text += f"1. {TEXT_HELP} - Show this help message\n"
    help_text += f"2. {TEXT_ROLL} - Roll the dice\n"
    return help_text