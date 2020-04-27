import json
import os
import sys

from common import bot_strategy_names

if len(sys.argv) < 2:
    exit(0)

bot = sys.argv[1].strip()
username = f"katrain-{bot}"
greetings = {
    "dev": "Experimental!",
    "strong": "Play top policy move.",
    "influence": "Play an influential style.",
    "territory": "Play a territorial style.",
    "balanced": "Play the best move out of a random selection.",
    "weighted": "Play a policy-weighted move.",
    "local": "Prefer local responses.",
    "tenuki": "Prefer to tenuki.",
}
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
GREETING = (
    f"Hello, welcome to an experimental version of KaTrain AIs - These are based on weakened policy nets of KataGo. Current mode is: {greetings[bot]}. Settings: {settings_dump} "
)
BYEMSG = "Thank you for playing. If you have any feedback, please message my admin!"
MAXGAMES = 10
os.system(
    f'gtp2ogs --apikey {APIKEY} --username {username} --greeting "{GREETING}" --rankedonly  --farewell "{BYEMSG}" --ogspv katago --noclock --speeds blitz,live --maxconnectedgames {MAXGAMES} --persist --minrank 20k --noautohandicap --maxhandicap 0 --boardsizes 9,13,19 --komis automatic,6.5 -- python ai2gtp.py {bot}'
)
