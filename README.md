# d20potz
d20 board games helper bot for Telegram

## Configuration
make a symlink ./shared -> potz-shared library

## everything below is deprecated

## How to run
**$** *pip3 install python-telegram-bot --upgrade --pre*
**$** *pip3 install leveldb*
**$** *touch d20potz.cfg* # and fill [bot] section with parameters: **db\_dir** and **telegram\_token**
**$** *python3 d20potz.py*


## Configuration file format
Here is minimal content of *d20potz.cfg*: <pre>
[bot]
db_dir = ./d20potzdb
telegram_token = very-secret-token
</pre>
