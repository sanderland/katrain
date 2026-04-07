#!/usr/bin/env python3
"""Generate v003 package with inline board payloads and narrations (no API calls).

Positions derived from visual analysis of cropped book figures.
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from lib.audio_gen import generate_audio_sync

REPO_ROOT = Path(__file__).parent.parent
DATA_DIR = REPO_ROOT / "data" / "tutorials_published"
VERSION = "v003"
VERSION_DIR = DATA_DIR / "versions" / VERSION
AUDIO_DIR = VERSION_DIR / "assets" / "audio"
CATEGORIES_DIR = VERSION_DIR / "categories"
TOPICS_DIR = VERSION_DIR / "topics" / "chapter1"
EXAMPLES_DIR = VERSION_DIR / "examples"

# ─── Inline content ────────────────────────────────────────────────────────────
# Each step: (book_text, narration, board_payload)
STEPS_DATA = {
    # ex_s1_001 — 外势与实地的基本含义
    ("ex_s1_001", 1): {
        "book_text": "图1中的黑1我们称之为三三，是三线与三线的交叉点，也是实地线与实地线的交叉点。其优点是在确保眼位方面比较容易，缺点是向边和中腹的发展能力比较弱。白2是四线与四线的交叉点，称之为\"星\"，也是外势线与外势线的交叉点。其优点是向边和中腹的发展能力比较强，缺点是在实地形成方面比较弱，性质正好和三三相反。",
        "narration": "黑棋占据三三时，棋子位于第三条线的交叉点，最大优势在于容易确保眼位，稳扎稳打地积累实地；但发展潜力受限，向边路和中腹延伸的力量相对薄弱。相比之下，白棋占据星位，落在第四条线，向外扩张的能力极为突出，能够影响边路和中腹的广大范围，却在角地的实利方面较为薄弱。两者各有侧重，性质恰好相反。",
        "board_payload": {
            "size": 19,
            "stones": {"B": [[2, 16]], "W": [[3, 3]]},
            "labels": {"2,16": "1", "3,3": "2"},
            "highlights": [],
            "viewport": {"col": 0, "row": 0, "size": 17}
        },
        "book_figure_asset": "assets/book_figures/p011_fig1.png",
    },
    ("ex_s1_001", 2): {
        "book_text": "图2中，黑1点三三，则角上的主人就变为黑棋了。但是黑棋取得实地的同时，白棋却获取了外势。白棋的外势向A方面和中腹发展的可能性很大，完全有能力挽回被黑棋获取实地的损失。",
        "narration": "黑棋突入三三，牢牢掌控了角部实地，看似得到了实利。然而正当黑棋在角里安顿之时，白棋凭借应对手段积累起强大的外势。这股外势无论向边路延伸还是向中腹扩展，都潜力巨大，足以弥补角部让出的损失。实地虽属黑棋，大局却未必落后。",
        "board_payload": {
            "size": 19,
            "stones": {
                "B": [[2, 2], [3, 2], [1, 3], [1, 4], [3, 1], [2, 15]],
                "W": [[3, 3], [2, 3], [2, 4], [2, 5], [2, 1], [4, 1]]
            },
            "labels": {
                "2,2": "1", "2,3": "2", "3,2": "3", "2,4": "4",
                "1,3": "5", "2,5": "6", "1,4": "7", "2,1": "8",
                "3,1": "9", "4,1": "10"
            },
            "highlights": [],
            "viewport": {"col": 0, "row": 0, "size": 9}
        },
        "book_figure_asset": "assets/book_figures/p011_fig2.png",
    },
    # ex_s1_002 — 取实地和外势的手段
    ("ex_s1_002", 1): {
        "book_text": "图3的白1是阻碍黑棋发展并获取自身外势的基本手法。黑2以下至黑6，黑棋获得了实地，但是到白7时，白棋也获取了充分的外势。三三在获取实地方面是优点，但在向边和中腹发展方面却有缺点。那么实地和外势，其中哪一个更为重要呢？低级棋手往往更为重视实地，其实外势与实地同样重要。",
        "narration": "白棋在图3中率先落子，选择一手压制黑棋发展、同时为自己构筑外势的要点。此后黑棋按部就班走出实地，白棋则借势完成宽广的外势阵型。三三虽善于积累角地，却在向外扩展时显现出不足。实地与外势究竟孰轻孰重？初学者常常更偏爱看得见的实地，但事实上两者在棋局中的价值不分伯仲。",
        "board_payload": {
            "size": 19,
            "stones": {
                "B": [[2, 10], [0, 10], [2, 8]],
                "W": [[3, 3], [2, 9], [3, 10], [3, 11], [7, 10]]
            },
            "labels": {
                "2,9": "1", "2,10": "2", "3,10": "3",
                "0,10": "4", "2,8": "5", "3,11": "6", "7,10": "7"
            },
            "highlights": [],
            "viewport": {"col": 0, "row": 6, "size": 9}
        },
        "book_figure_asset": "assets/book_figures/p012_fig3.png",
    },
    ("ex_s1_002", 2): {
        "book_text": "图4中的黑1是让白棋获取实地而自身获取外势时的常用手段。白棋到白4为止，白棋首先获取了实地，但黑棋以外势作后盾，在5位扩张，黑棋也很充分。但如果使白棋获得实地，而自己所取的外势价值不大，则会对黑棋不利，所以应慎重利用黑1、3这样的手段。",
        "narration": "图4展示了一种主动礼让角地、换取外势的策略。黑棋先出手，引导白棋占据实地，自己则趁势建立起宽广的外势。白棋到第四手为止稳固了实地，而黑棋凭借厚势在边路5位展开，双方各得所需。不过这种下法需要审慎：若换来的外势发展空间有限、价值不足，反而会令黑棋处于不利局面，因此运用时务必权衡清楚。",
        "board_payload": {
            "size": 19,
            "stones": {
                "B": [[3, 1], [4, 1], [2, 7], [2, 15]],
                "W": [[3, 3], [3, 2], [4, 2], [2, 2]]
            },
            "labels": {
                "3,1": "1", "3,2": "2", "4,1": "3", "2,2": "4", "2,7": "5"
            },
            "highlights": [],
            "viewport": {"col": 0, "row": 0, "size": 11}
        },
        "book_figure_asset": "assets/book_figures/p012_fig4.png",
    },
    # ex_s1_003 — 实地与外势的均势
    ("ex_s1_003", 1): {
        "book_text": "图5中白1托是白棋占取实地时所常用的手法。下至白5，白棋先手占取了相当的实地。但也应注意黑棋同时也获得了外势。黑棋以外势作后盾，在6位展开，黑棋的外势充分有能力和白棋的实地相抗衡，结果是白棋的实地与黑棋的外势形成了均势。因此在布局阶段，实地和外势同样重要。",
        "narration": "白棋以「托」的手法率先发力，这是布局阶段常见的夺取角地手段。白棋五手落定，以先手姿态牢牢握住了一块实地。但与此同时，黑棋也在这场交换中积蓄起强大的外势。以这股外势为依托，黑棋随即在6位向边路展开。最终的结局是：白棋实地与黑棋外势势均力敌，各有千秋。这正说明，布局阶段不可偏废——实地与外势，同等重要。",
        "board_payload": {
            "size": 19,
            "stones": {
                "B": [[2, 2], [2, 3], [2, 8]],
                "W": [[3, 3], [1, 2], [1, 1], [2, 1], [0, 2]]
            },
            "labels": {
                "1,2": "1", "2,2": "2", "1,1": "3", "2,3": "4",
                "0,2": "5", "2,8": "6"
            },
            "highlights": [],
            "viewport": {"col": 0, "row": 0, "size": 11}
        },
        "book_figure_asset": "assets/book_figures/p013_fig5.png",
    },
    ("ex_s1_003", 2): {
        "book_text": "图6中黑1飞封是取外势时使用的手段。白2以下至黑9，黑棋如愿以偿获取了外势，并有可能向边和中央发展。但是在取外势的同时，也使白棋取得了实地。将来根据黑棋外势的利用如何，将决定黑棋的有利或不利。",
        "narration": "黑棋采用「飞封」手法，一跃封锁白棋的角地，主动追求外势。经过随后的数手往来，黑棋如愿构筑起连绵的外势阵型，蓄势待发，随时可以向边路或中腹延伸。然而此番取势，也让白棋在角里坐享实地。这局棋最终的胜负，将由黑棋是否能充分利用这片外势来决定——善用则优，滥用则劣。",
        "board_payload": {
            "size": 19,
            "stones": {
                "B": [[3, 2], [4, 2], [2, 3], [2, 4], [4, 1], [2, 15]],
                "W": [[2, 1], [3, 1], [2, 2], [2, 5]]
            },
            "labels": {
                "3,2": "1", "2,1": "2", "4,2": "3", "2,2": "4",
                "2,3": "5", "2,5": "6", "2,4": "7", "3,1": "8", "4,1": "9"
            },
            "highlights": [],
            "viewport": {"col": 0, "row": 0, "size": 9}
        },
        "book_figure_asset": "assets/book_figures/p013_fig6.png",
    },
    # ex_s1_004 — 外势的价值判断
    ("ex_s1_004", 1): {
        "book_text": "黑1点三三可以轻易取得实地。但白2以下至白12，白棋取得了很厚的外势，结果黑棋非常不利。与黑棋所取得的实地相比，白棋的外势在左边筑起了很大的模样，而且向中腹发展的可能性很大。在布局初期，不能因取实地而招致不利，必须要有协调外势和实地的能力。",
        "narration": "黑棋突入三三，看似轻松到手一块实地；然而白棋借此机会，从第二手起连续运子，直至十二手，在左侧筑起极为厚实的外势阵营。与黑棋所得实地相比，白棋的外势既宽且厚，向中腹延伸的潜力无穷，黑棋陷入明显的劣势。布局之初，切不可只顾眼前实地而忽视全局大势——协调外势与实地的能力，正是优秀布局的关键。",
        "board_payload": {
            "size": 19,
            "stones": {
                "B": [[2, 2], [3, 2], [2, 1], [3, 0], [1, 3], [0, 3]],
                "W": [[3, 3], [2, 3], [4, 2], [3, 1], [4, 1], [5, 2], [1, 2], [0, 2], [1, 8], [1, 14]]
            },
            "labels": {
                "2,2": "1", "2,3": "2", "3,2": "3", "4,2": "4",
                "2,1": "5", "3,1": "6", "3,0": "7", "4,1": "8",
                "1,3": "9", "1,2": "10", "0,3": "11", "0,2": "12"
            },
            "highlights": [],
            "viewport": {"col": 0, "row": 0, "size": 9}
        },
        "book_figure_asset": "assets/book_figures/p014_fig7.png",
    },
    ("ex_s1_004", 2): {
        "book_text": "白1托是获取实地的常用手法，前面已有阐述。黑2以下进行至白5为止，白棋如愿以偿地得到了实地，但黑棋所取得的外势因白△的影响，而没有价值。应该时常牢记，取外势时，不能取无发展可能性的外势，那样会招致不利。",
        "narration": "白棋同样以「托」起手，向角地展开进攻。黑棋如法炮制，以同一套应对手段取得了外势，白棋也到位拿到实地。然而这次的结果截然不同——黑棋虽得外势，却因白△的存在被压缩殆尽，毫无发展余地。这是一个深刻的警示：取外势时，必须审视这片势力是否有充分的发展空间。若换来的外势毫无用武之地，便是弃子换空，得不偿失。",
        "board_payload": {
            "size": 19,
            "stones": {
                "B": [[2, 2], [2, 3], [2, 7]],
                "W": [[1, 2], [1, 1], [2, 1], [0, 2], [3, 3]]
            },
            "labels": {
                "1,2": "1", "2,2": "2", "1,1": "3", "2,3": "4", "0,2": "5"
            },
            "highlights": [[2, 7]],
            "viewport": {"col": 0, "row": 0, "size": 10}
        },
        "book_figure_asset": "assets/book_figures/p014_fig8.png",
    },
    # ex_s1_005 — 正确把握方向
    ("ex_s1_005", 1): {
        "book_text": "对白△的托，黑1、3的方向才正确，应转取上边的外势。\n如何灵活获取和利用外势很重要。成功的布局应协调好外势与实地的关系，不仅要取得实地，也要获取外势。",
        "narration": "面对白棋的「托」，正确的应对并非执着于守住角地，而是以黑1、3转向边路，主动争取上边的外势。方向的选择，往往比单纯得失更为关键。布局的艺术在于统筹全局：一方面要落实实地，另一方面也要把握外势——只有两者兼顾、相互配合，才能在布局阶段奠定胜局的基础。",
        "board_payload": {
            "size": 19,
            "stones": {
                "B": [[2, 3], [3, 3], [2, 14]],
                "W": [[2, 1], [1, 3], [2, 6], [3, 1]]
            },
            "labels": {
                "2,3": "1", "1,3": "2", "3,3": "3"
            },
            "highlights": [[1, 3]],
            "viewport": {"col": 0, "row": 0, "size": 10}
        },
        "book_figure_asset": "assets/book_figures/p015_fig9.png",
    },
    ("ex_s1_005", 2): {
        "book_text": "白1时，黑2靠压虽是巩固自身时的常用手段，但黑2以下进行至白13为止，由于黑●过于接近黑棋庞大的外势，黑棋不满。相反白棋与白△保持较适当的间隔，白棋满足。黑●如果位于A位或B位，在一定程度上可以加大外势的影响力，黑棋还充分可下。",
        "narration": "白棋出手，黑棋以「靠压」应对——这本是加固自身的常规手段。然而随着双方十三手棋的展开，问题逐渐浮现：黑棋新下的棋子（黑●）与自身原有的外势过于紧凑，毫无张力可言，反而削弱了那片势力的影响范围。反观白棋，借助白△形成了适度间隔，布置从容，颇为满意。若黑●改落A位或B位，与外势保持更合理的距离，方能充分发挥外势的效能，黑棋局面依然充分。",
        "board_payload": {
            "size": 19,
            "stones": {
                "B": [[4, 9], [3, 10], [2, 10], [2, 11], [3, 12], [4, 9]],
                "W": [[3, 9], [3, 8], [4, 10], [2, 9], [3, 11], [4, 11], [3, 7], [2, 3]]
            },
            "labels": {
                "3,9": "1", "4,9": "2", "3,8": "3", "3,10": "4",
                "2,9": "5", "2,10": "6", "3,11": "7", "2,11": "8",
                "4,10": "9", "3,12": "10", "4,11": "11", "3,13": "12", "4,8": "13"
            },
            "highlights": [[2, 3], [4, 9]],
            "viewport": {"col": 0, "row": 6, "size": 11}
        },
        "book_figure_asset": "assets/book_figures/p015_fig10.png",
    },
}

CATEGORY = {"id": "cat_chapter1", "slug": "chapter1", "title": "布局入门", "summary": "曹薰铉布局技巧第一章：掌握围棋布局的基础概念与手法", "order": 1}
TOPIC = {"id": "topic_ch1_s1", "category_id": "cat_chapter1", "slug": "s1-势-vs-地", "title": "外势和实地", "summary": "理解外势与实地的基本含义，以及布局中如何平衡两者"}
EXAMPLES_META = [
    {"id": "ex_s1_001", "topic_id": "topic_ch1_s1", "title": "外势与实地的基本含义", "summary": "三三与星位：实地与外势的基本区别", "order": 1},
    {"id": "ex_s1_002", "topic_id": "topic_ch1_s1", "title": "取实地和外势的手段", "summary": "阻止发展与利用外势的常用布局手法", "order": 2},
    {"id": "ex_s1_003", "topic_id": "topic_ch1_s1", "title": "实地与外势的均势", "summary": "外势与实地相抗衡时的均势局面", "order": 3},
    {"id": "ex_s1_004", "topic_id": "topic_ch1_s1", "title": "外势的价值判断", "summary": "如何判断外势是否有价值，避免取得无效外势", "order": 4},
    {"id": "ex_s1_005", "topic_id": "topic_ch1_s1", "title": "正确把握方向", "summary": "方向的选择对外势价值的影响", "order": 5},
]


def ensure_dirs():
    for d in [AUDIO_DIR, CATEGORIES_DIR, TOPICS_DIR, EXAMPLES_DIR]:
        d.mkdir(parents=True, exist_ok=True)


def step_id(ex_id: str, order: int) -> str:
    num = ex_id.replace("ex_s1_", "")
    return f"step_s1_{num}_{order:03d}"


def write_json(path: Path, data: dict):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def main():
    print(f"=== Generating tutorial {VERSION} (inline data) ===\n")
    ensure_dirs()

    for ex_meta in EXAMPLES_META:
        ex_id = ex_meta["id"]
        print(f"\n[{ex_id}] {ex_meta['title']}")
        steps_out = []
        for order in [1, 2]:
            key = (ex_id, order)
            data = STEPS_DATA[key]
            sid = step_id(ex_id, order)

            audio_path = AUDIO_DIR / f"{sid}.mp3"
            print(f"  Step {order}: TTS → {audio_path.name}")
            generate_audio_sync(data["narration"], str(audio_path))

            steps_out.append({
                "id": sid,
                "example_id": ex_id,
                "order": order,
                "narration": data["narration"],
                "image_asset": None,
                "audio_asset": f"assets/audio/{sid}.mp3",
                "audio_duration_ms": None,
                "board_mode": "sgf",
                "board_payload": data["board_payload"],
                "book_figure_asset": data["book_figure_asset"],
                "book_text": data["book_text"],
            })

        ex_json = {**ex_meta, "total_duration_sec": None, "step_count": 2, "steps": steps_out}
        write_json(EXAMPLES_DIR / f"{ex_id}.json", ex_json)
        print(f"  Written → examples/{ex_id}.json")

    # Topic
    write_json(TOPICS_DIR / f"{TOPIC['slug']}.json", {
        **TOPIC,
        "tags": ["外势", "实地", "布局基础"],
        "difficulty": "beginner",
        "estimated_minutes": 15,
        "example_ids": [ex["id"] for ex in EXAMPLES_META],
    })

    # Category
    write_json(CATEGORIES_DIR / f"{CATEGORY['slug']}.json", {**CATEGORY, "topic_count": 1, "cover_asset": None})

    # Manifest
    write_json(VERSION_DIR / "manifest.json", {
        "version": VERSION,
        "published_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "categories": [CATEGORY["slug"]],
        "stats": {"categories": 1, "topics": 1, "examples": 5, "steps": 10},
    })

    # active.json
    write_json(DATA_DIR / "active.json", {"version": VERSION, "path": f"versions/{VERSION}"})
    print(f"\n[active.json] → {VERSION}")

    n_audio = len(list(AUDIO_DIR.glob("*.mp3")))
    print(f"\n=== Done — {n_audio} audio files ===")


if __name__ == "__main__":
    main()
