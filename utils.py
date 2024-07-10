import logging

from texts import TEXT_HELP, TEXT_ROLL

def setup_logging(level: int, name: str) -> logging.Logger:
    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.WARNING
    )

    new_logger = logging.getLogger(name)
    new_logger.setLevel(level)
    return new_logger

logger = setup_logging(logging.INFO, __name__)


def get_client_help_message() -> str:
    """
    Returns the help message for the client
    """
    help_text = "What can this bot do?\n\n"
    help_text += f"1. {TEXT_HELP} - Show this help message\n"
    help_text += f"2. {TEXT_ROLL} - Roll the dice\n"
    return help_text