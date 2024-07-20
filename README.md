# d20potz
d20 board games helper bot for Telegram

## How to run
**$** pull/symlink https://github.com/nightshadows/potz-shared into ./shared
**$** ./build_zip.sh
**$** upload d20potz.zip to AWS lambda
**$** you will need a lambda layer containing boto3 and python-telegram-bot
**$** put your telegram bot token into TELEGRAM_TOKEN env variable in lambda
