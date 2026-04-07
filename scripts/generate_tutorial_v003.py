#!/usr/bin/env python3
"""Generate tutorial v003 package — book-faithful content with split layout.

Content: Chapter 1, Section 1 — 外势和实地 (10 figures, pages 11–15)
Each example has 2 steps (2 figures each), 5 examples total.

Usage:
    python scripts/generate_tutorial_v003.py

Output:
    data/tutorials_published/versions/v003/   — full package tree
    data/tutorials_published/active.json      — updated to v003
"""
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

# Ensure scripts/lib is on the path
sys.path.insert(0, str(Path(__file__).parent))

from lib.figure_cropper import crop_figure
from lib.board_recognizer import recognize_board
from lib.narration_rewriter import rewrite_narration
from lib.audio_gen import generate_audio_sync

# ─── Paths ────────────────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).parent.parent
BOOK_DIR = Path("/Users/fan/Repositories/go-topic-collections/books/布局/曹薰铉布局技巧_上册_曹薰铉_1997/output")
BOOK_PAGES_DIR = BOOK_DIR / "pages"
BOOK_JSONL = BOOK_DIR / "extracted.jsonl"

DATA_DIR = REPO_ROOT / "data" / "tutorials_published"
VERSION = "v003"
VERSION_DIR = DATA_DIR / "versions" / VERSION

BOOK_FIGURES_DIR = VERSION_DIR / "assets" / "book_figures"
AUDIO_DIR = VERSION_DIR / "assets" / "audio"
CATEGORIES_DIR = VERSION_DIR / "categories"
TOPICS_DIR = VERSION_DIR / "topics" / "chapter1"
EXAMPLES_DIR = VERSION_DIR / "examples"

# ─── Content definition ────────────────────────────────────────────────────────
CATEGORY = {
    "id": "cat_chapter1",
    "slug": "chapter1",
    "title": "布局入门",
    "summary": "曹薰铉布局技巧第一章：掌握围棋布局的基础概念与手法",
    "order": 1,
}

TOPIC = {
    "id": "topic_ch1_s1",
    "category_id": "cat_chapter1",
    "slug": "s1-势-vs-地",
    "title": "外势和实地",
    "summary": "理解外势与实地的基本含义，以及布局中如何平衡两者",
    "example_ids": ["ex_s1_001", "ex_s1_002", "ex_s1_003", "ex_s1_004", "ex_s1_005"],
}

EXAMPLES_META = [
    {
        "id": "ex_s1_001",
        "topic_id": "topic_ch1_s1",
        "title": "外势与实地的基本含义",
        "summary": "三三与星位：实地与外势的基本区别",
        "order": 1,
        "pages": [11, 11],
        "figure_labels": ["图1", "图2"],
    },
    {
        "id": "ex_s1_002",
        "topic_id": "topic_ch1_s1",
        "title": "取实地和外势的手段",
        "summary": "阻止发展与利用外势的常用布局手法",
        "order": 2,
        "pages": [12, 12],
        "figure_labels": ["图3", "图4"],
    },
    {
        "id": "ex_s1_003",
        "topic_id": "topic_ch1_s1",
        "title": "实地与外势的均势",
        "summary": "外势与实地相抗衡时的均势局面",
        "order": 3,
        "pages": [13, 13],
        "figure_labels": ["图5", "图6"],
    },
    {
        "id": "ex_s1_004",
        "topic_id": "topic_ch1_s1",
        "title": "外势的价值判断",
        "summary": "如何判断外势是否有价值，避免取得无效外势",
        "order": 4,
        "pages": [14, 14],
        "figure_labels": ["图7", "图8"],
    },
    {
        "id": "ex_s1_005",
        "topic_id": "topic_ch1_s1",
        "title": "正确把握方向",
        "summary": "方向的选择对外势价值的影响",
        "order": 5,
        "pages": [15, 15],
        "figure_labels": ["图9", "图10"],
    },
]


def load_book_data() -> dict[int, dict[str, dict]]:
    """Load extracted.jsonl and index figure_refs by (page, label)."""
    index: dict[int, dict[str, dict]] = {}
    with open(BOOK_JSONL, encoding="utf-8") as f:
        for line in f:
            entry = json.loads(line)
            page = entry["page"]
            for el in entry.get("elements", []):
                if el["type"] == "figure_ref":
                    index.setdefault(page, {})[el["label"]] = el
    return index


def step_id(example_id: str, step_order: int) -> str:
    ex_num = example_id.replace("ex_s1_", "")
    return f"step_s1_{ex_num}_{step_order:03d}"


def figure_asset(page: int, label: str) -> str:
    fig_num = label.replace("图", "")
    return f"assets/book_figures/p{page:03d}_fig{fig_num}.png"


def audio_asset_path(example_id: str, step_order: int) -> str:
    return f"assets/audio/{step_id(example_id, step_order)}.mp3"


def ensure_dirs() -> None:
    for d in [BOOK_FIGURES_DIR, AUDIO_DIR, CATEGORIES_DIR, TOPICS_DIR, EXAMPLES_DIR]:
        d.mkdir(parents=True, exist_ok=True)


def write_json(path: Path, data: dict) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def process_figure(page: int, label: str, fig_ref: dict, example_id: str, step_order: int) -> dict:
    """Crop, recognize, rewrite, and generate audio for one figure. Returns step dict."""
    book_text = fig_ref["text"]
    bbox = fig_ref["bbox"]

    # Step 1: Crop figure image
    page_img = BOOK_PAGES_DIR / f"page_{page:03d}.png"
    fig_asset = figure_asset(page, label)
    fig_out = VERSION_DIR / fig_asset
    print(f"    Cropping {page_img.name} → {fig_out.name}")
    crop_figure(page_img, bbox, fig_out, padding=0.02)

    # Step 2: Recognize board position
    print(f"    Recognizing board (Claude vision)…")
    try:
        board_payload = recognize_board(fig_out, book_text)
    except Exception as e:
        print(f"    [WARN] Board recognition failed: {e}")
        board_payload = {"size": 19, "stones": {"B": [], "W": []}, "labels": {}, "highlights": [], "viewport": None}

    # Step 3: Rewrite narration
    print(f"    Rewriting narration (Claude)…")
    try:
        narration = rewrite_narration(book_text)
    except Exception as e:
        print(f"    [WARN] Narration rewrite failed: {e}")
        narration = book_text  # fallback to original

    # Step 4: Generate TTS audio
    sid = step_id(example_id, step_order)
    audio_path = AUDIO_DIR / f"{sid}.mp3"
    print(f"    Generating TTS → {audio_path.name}")
    generate_audio_sync(narration, str(audio_path))

    return {
        "id": sid,
        "example_id": example_id,
        "order": step_order,
        "narration": narration,
        "image_asset": None,
        "audio_asset": audio_asset_path(example_id, step_order),
        "audio_duration_ms": None,
        "board_mode": "sgf",
        "board_payload": board_payload,
        "book_figure_asset": fig_asset,
        "book_text": book_text,
    }


def build_example_json(ex_meta: dict, steps: list[dict]) -> dict:
    return {
        "id": ex_meta["id"],
        "topic_id": ex_meta["topic_id"],
        "title": ex_meta["title"],
        "summary": ex_meta["summary"],
        "order": ex_meta["order"],
        "total_duration_sec": None,
        "step_count": len(steps),
        "steps": steps,
    }


def main() -> None:
    print(f"=== Generating tutorial {VERSION} ===\n")
    ensure_dirs()

    book_data = load_book_data()
    print(f"Loaded book data: {sum(len(v) for v in book_data.values())} figures across {len(book_data)} pages\n")

    # ── Generate assets + example JSONs ──────────────────────────────────────
    for ex_meta in EXAMPLES_META:
        print(f"\n[{ex_meta['id']}] {ex_meta['title']}")
        steps = []
        for step_order, (page, label) in enumerate(zip(ex_meta["pages"], ex_meta["figure_labels"]), start=1):
            print(f"  Step {step_order}: page {page}, {label}")
            fig_ref = book_data.get(page, {}).get(label)
            if not fig_ref:
                print(f"  [ERROR] Figure {label} not found on page {page}")
                continue
            step = process_figure(page, label, fig_ref, ex_meta["id"], step_order)
            steps.append(step)

        ex_json = build_example_json(ex_meta, steps)
        write_json(EXAMPLES_DIR / f"{ex_meta['id']}.json", ex_json)
        print(f"  Written → examples/{ex_meta['id']}.json")

    # ── Write topic JSON ──────────────────────────────────────────────────────
    print("\n[Topic]")
    topic_json = {
        "id": TOPIC["id"],
        "category_id": TOPIC["category_id"],
        "slug": TOPIC["slug"],
        "title": TOPIC["title"],
        "summary": TOPIC["summary"],
        "tags": ["外势", "实地", "布局基础"],
        "difficulty": "beginner",
        "estimated_minutes": 15,
        "example_ids": TOPIC["example_ids"],
    }
    write_json(TOPICS_DIR / f"{TOPIC['slug']}.json", topic_json)
    print(f"  Written → topics/chapter1/{TOPIC['slug']}.json")

    # ── Write category JSON ───────────────────────────────────────────────────
    print("\n[Category]")
    cat_json = {
        "id": CATEGORY["id"],
        "slug": CATEGORY["slug"],
        "title": CATEGORY["title"],
        "summary": CATEGORY["summary"],
        "order": CATEGORY["order"],
        "topic_count": 1,
        "cover_asset": None,
    }
    write_json(CATEGORIES_DIR / f"{CATEGORY['slug']}.json", cat_json)
    print(f"  Written → categories/{CATEGORY['slug']}.json")

    # ── Write manifest ────────────────────────────────────────────────────────
    total_steps = sum(len(ex["figure_labels"]) for ex in EXAMPLES_META)
    manifest = {
        "version": VERSION,
        "published_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "categories": [CATEGORY["slug"]],
        "stats": {
            "categories": 1,
            "topics": 1,
            "examples": len(EXAMPLES_META),
            "steps": total_steps,
        },
    }
    write_json(VERSION_DIR / "manifest.json", manifest)
    print(f"\n[Manifest] Written → manifest.json")

    # ── Update active.json ────────────────────────────────────────────────────
    active = {"version": VERSION, "path": f"versions/{VERSION}"}
    write_json(DATA_DIR / "active.json", active)
    print(f"[active.json] Updated → {VERSION}\n")

    # ── Summary ───────────────────────────────────────────────────────────────
    n_figures = len(list(BOOK_FIGURES_DIR.glob("*.png")))
    n_audio = len(list(AUDIO_DIR.glob("*.mp3")))
    print(f"=== Done ===")
    print(f"  Book figures: {n_figures}  Audio: {n_audio}")
    print(f"  Package: {VERSION_DIR}")


if __name__ == "__main__":
    main()
