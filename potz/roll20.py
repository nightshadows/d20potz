#! /usr/bin/env python3
# -*- coding: utf-8 -*-

import random

from telegram import Update
from telegram.ext import ContextTypes

async def roll20(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="Rolling... {}".format(random.SystemRandom().randint(1, 20)),
    )