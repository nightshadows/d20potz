

from dataclasses import dataclass, field


@dataclass
class BotData:
    user_id: int
    user_name: str
    chat_id: int
    params : list[str] = field(default_factory=list)

    def __init__(self, update):
        message = update.message
        if not message:
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


    def sync(self):
        pass
