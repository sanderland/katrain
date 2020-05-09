bot_strategy_names = {
    # "dev": "P:Noise",
    "dev": "ScoreLoss",
    "dev-beta": "P:Weighted",
    "strong": "Policy",
    "influence": "P:Influence",
    "territory": "P:Territory",
    "balanced": "P:Pick",
    "weighted": "P:Weighted",
    "local": "P:Local",
    "tenuki": "P:Tenuki",
}


greetings = {
    #    "dev": "Policy+Dirichlet noise.",
    "dev": "Point loss-weighted random move.",
    "dev-beta": "Play a policy-weighted move.",
    "strong": "Play top policy move.",
    "influence": "Play an influential style.",
    "territory": "Play a territorial style.",
    "balanced": "Play the best move out of a random selection.",
    "weighted": "Play a policy-weighted move.",
    "local": "Prefer local responses.",
    "tenuki": "Prefer to tenuki.",
}
