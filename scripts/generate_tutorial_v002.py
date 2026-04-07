#!/usr/bin/env python3
"""Generate tutorial v002 package with real board diagrams and TTS audio.

Usage:
    python scripts/generate_tutorial_v002.py

Output:
    data/tutorials_published/versions/v002/   — full package tree
    data/tutorials_published/active.json      — updated to v002
"""
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Ensure scripts/lib is on the path
sys.path.insert(0, str(Path(__file__).parent))

from lib.board_renderer import render_board
from lib.audio_gen import generate_audio_sync
from lib.v002_content import CATEGORY, TOPICS, EXAMPLES

# ─── Paths ────────────────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).parent.parent
DATA_DIR = REPO_ROOT / "data" / "tutorials_published"
VERSION = "v002"
VERSION_DIR = DATA_DIR / "versions" / VERSION

IMAGES_DIR = VERSION_DIR / "assets" / "images"
AUDIO_DIR = VERSION_DIR / "assets" / "audio"
CATEGORIES_DIR = VERSION_DIR / "categories"
TOPICS_DIR = VERSION_DIR / "topics" / "opening"
EXAMPLES_DIR = VERSION_DIR / "examples"


def ensure_dirs():
    for d in [IMAGES_DIR, AUDIO_DIR, CATEGORIES_DIR, TOPICS_DIR, EXAMPLES_DIR]:
        d.mkdir(parents=True, exist_ok=True)


def step_id(example_id: str, step_order: int) -> str:
    ex_num = example_id.replace("ex_opening_", "")
    return f"step_ex{ex_num}_{step_order:03d}"


def image_asset(example_id: str, step_order: int) -> str:
    return f"assets/images/{step_id(example_id, step_order)}.png"


def audio_asset(example_id: str, step_order: int) -> str:
    return f"assets/audio/{step_id(example_id, step_order)}.mp3"


def generate_step_assets(example_id: str, step: dict, order: int) -> None:
    sid = step_id(example_id, order)

    # Board image
    img_path = IMAGES_DIR / f"{sid}.png"
    print(f"  Rendering board → {img_path.name}")
    img = render_board(
        stones=step["stones"],
        board_size=19,
        image_px=400,
        highlights=step.get("highlights"),
    )
    img.save(img_path, "PNG")

    # Audio
    audio_path = AUDIO_DIR / f"{sid}.mp3"
    print(f"  Generating TTS  → {audio_path.name}")
    generate_audio_sync(step["narration"], str(audio_path))


def build_example_json(ex: dict) -> dict:
    steps_out = []
    for i, step in enumerate(ex["steps"], start=1):
        sid = step_id(ex["id"], i)
        steps_out.append(
            {
                "id": sid,
                "example_id": ex["id"],
                "order": i,
                "narration": step["narration"],
                "image_asset": image_asset(ex["id"], i),
                "audio_asset": audio_asset(ex["id"], i),
                "audio_duration_ms": None,
                "board_mode": "image",
                "board_payload": None,
            }
        )
    return {
        "id": ex["id"],
        "topic_id": ex["topic_id"],
        "title": ex["title"],
        "summary": ex["summary"],
        "order": ex["order"],
        "total_duration_sec": None,
        "step_count": len(ex["steps"]),
        "steps": steps_out,
    }


def build_topic_json(topic: dict) -> dict:
    return {
        "id": topic["id"],
        "category_id": topic["category_id"],
        "slug": topic["slug"],
        "title": topic["title"],
        "summary": topic["summary"],
        "tags": None,
        "difficulty": None,
        "estimated_minutes": None,
        "example_ids": topic["example_ids"],
    }


def build_category_json(total_topics: int) -> dict:
    return {
        "id": CATEGORY["id"],
        "slug": CATEGORY["slug"],
        "title": CATEGORY["title"],
        "summary": CATEGORY["summary"],
        "order": CATEGORY["order"],
        "topic_count": total_topics,
        "cover_asset": None,
    }


def write_json(path: Path, data: dict) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def main():
    print(f"=== Generating tutorial {VERSION} ===\n")
    ensure_dirs()

    total_steps = sum(len(ex["steps"]) for ex in EXAMPLES)
    print(
        f"Content: {len(TOPICS)} topics, {len(EXAMPLES)} examples, {total_steps} steps\n"
    )

    # ── Generate assets + example JSONs ──────────────────────────────────────
    for ex in EXAMPLES:
        print(f"\n[{ex['id']}] {ex['title']}")
        for i, step in enumerate(ex["steps"], start=1):
            print(f"  Step {i}/{len(ex['steps'])}")
            generate_step_assets(ex["id"], step, i)

        ex_json = build_example_json(ex)
        write_json(EXAMPLES_DIR / f"{ex['id']}.json", ex_json)
        print(f"  Written → examples/{ex['id']}.json")

    # ── Write topic JSONs ─────────────────────────────────────────────────────
    print("\n[Topics]")
    for topic in TOPICS:
        topic_json = build_topic_json(topic)
        write_json(TOPICS_DIR / f"{topic['slug']}.json", topic_json)
        print(f"  Written → topics/opening/{topic['slug']}.json")

    # ── Write category JSON ───────────────────────────────────────────────────
    print("\n[Category]")
    cat_json = build_category_json(len(TOPICS))
    write_json(CATEGORIES_DIR / f"{CATEGORY['slug']}.json", cat_json)
    print(f"  Written → categories/{CATEGORY['slug']}.json")

    # ── Write manifest ────────────────────────────────────────────────────────
    manifest = {
        "version": VERSION,
        "published_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "categories": [CATEGORY["slug"]],
        "stats": {
            "categories": 1,
            "topics": len(TOPICS),
            "examples": len(EXAMPLES),
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
    n_images = len(list(IMAGES_DIR.glob("*.png")))
    n_audio = len(list(AUDIO_DIR.glob("*.mp3")))
    print(f"=== Done ===")
    print(f"  Images: {n_images}  Audio: {n_audio}")
    print(f"  Package: {VERSION_DIR}")


if __name__ == "__main__":
    main()
