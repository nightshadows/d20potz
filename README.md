# d20potz
d20 board games helper bot for Telegram

## How to run
**$** *pip3 install python-telegram-bot --upgrade --pre*
**$** *pip3 install leveldb*  
**$** *touch d20potz.cfg* # and fill [bot] section with parameters: **db\_dir** and **telegram\_token**  
**$** *python2 yachbot.py* 


## Configuration file format
Here is minimal content of *d20potz.cfg*: <pre>
[bot]
db_dir = ./d20potzdb
telegram_token = very-secret-token
</pre>
