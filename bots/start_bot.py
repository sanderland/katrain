import json
import os
import sys
from bots.settings import bot_strategy_names, greetings

if len(sys.argv) < 2:
    exit(0)

bot = sys.argv[1].strip()
port = int(sys.argv[2]) if len(sys.argv) > 2 else 8587

MAXGAMES = 10
if True or bot in ["dev", "local"]:
    GTP2OGS = "node ../gtp2ogs"
else:
    GTP2OGS = "node ../stable-gtp2ogs"
BOT_SETTINGS = f" --maxconnectedgames {MAXGAMES} --maxhandicapunranked 25 --maxhandicapranked 1 --boardsizesranked 19 --boardsizesunranked all --komisranked automatic,5.5,6.5,7.5 --komisunranked all"
if "beta" in bot:
    BOT_SETTINGS += " --beta"
else:
    BOT_SETTINGS += " --rankedonly"

username = f"katrain-{bot}"

with open("config.json") as f:
    settings = json.load(f)
    all_ai_settings = settings["ai"]

ai_settings = all_ai_settings[bot_strategy_names[bot]]

with open("my/apikey.json") as f:
    apikeys = json.load(f)

if bot not in greetings or username not in apikeys:
    print("BOT NOT FOUND")
    exit(1)

APIKEY = apikeys[username]
settings_dump = ", ".join(f"{k}={v}" for k, v in ai_settings.items() if not k.startswith("_"))
print(settings_dump)
GREETING = f"Hello, welcome to an experimental version of KaTrain AIs - These are based on weakened policy nets of KataGo. Current mode is: {greetings[bot]}"
if settings:
    GREETING += f" Settings: {settings_dump}."
BYEMSG = "Thank you for playing. If you have any feedback, please message my admin! Play with these bots at any time by downloading KaTrain at github.com/sanderland/katrain"

cmd = f'{GTP2OGS} --debug --apikey {APIKEY} --rejectnewfile ~/shutdown_bots --username {username} --greeting "{GREETING}" --farewell "{BYEMSG}"  {BOT_SETTINGS} --farewellscore --aichat --noclock --nopause --speeds blitz,live  --persist --minrank 25k  -- python bots/ai2gtp.py {bot} {port}'
print(f"starting bot {username} using server port {port} --> {cmd}")
os.system(cmd)
