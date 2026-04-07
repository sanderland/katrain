#!/usr/bin/env python3
"""Generate narration text + TTS audio for tutorial figures.

For each figure in a section:
  1. Rewrite book_text → narration via claude CLI (Max subscription) or Anthropic API
  2. Generate TTS audio via edge-tts (or CosyVoice if configured)
  3. Save narration + audio_asset path to database

Usage:
    python scripts/generate_voice.py --section-id <ID>
    python scripts/generate_voice.py --section-id <ID> --concurrency 8
    python scripts/generate_voice.py --section-id <ID> --rewriter api   # Use Anthropic API instead of CLI
    python scripts/generate_voice.py --section-id <ID> --force          # Re-generate all
    python scripts/generate_voice.py --section-id <ID> --dry-run        # Preview only
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path

# Ensure project root is on path
REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT))

from katrain.web.core.db import SessionLocal
from katrain.web.core.models_db import TutorialFigure, TutorialSection, TutorialBook, TutorialChapter

NARRATION_PROMPT = """You are helping create Go (围棋) tutorial narration for learners.

Rewrite the following Chinese Go book text. Requirements:
- Keep ALL concepts, technical terms, and strategic content intact
- Rephrase sentence structure and word choice so it doesn't feel like a direct copy
- Maintain the same level of detail and meaning
- Write in natural, clear Mandarin Chinese suitable for a digital tutorial
- Use a warm, conversational tone as if explaining to a student
- Output ONLY the rewritten Chinese text — no translation, no explanation, no quotes

Original text:
{text}"""


def get_book_slug(db, section_id: int) -> str:
    """Resolve book slug from section_id."""
    section = db.query(TutorialSection).filter_by(id=section_id).first()
    if not section:
        raise ValueError(f"Section {section_id} not found")
    chapter = db.query(TutorialChapter).filter_by(id=section.chapter_id).first()
    book = db.query(TutorialBook).filter_by(id=chapter.book_id).first()
    return book.slug


# ---------------------------------------------------------------------------
# Narration rewriters
# ---------------------------------------------------------------------------

async def rewrite_narration_cli(book_text: str, model: str = "sonnet") -> str:
    """Rewrite book text via claude CLI (uses Max subscription, no API cost)."""
    prompt = NARRATION_PROMPT.format(text=book_text)
    # Strip ANTHROPIC_API_KEY so claude CLI uses Max subscription OAuth, not API billing
    env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
    proc = await asyncio.create_subprocess_exec(
        "claude", "-p", "--model", model,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
    )
    stdout, stderr = await proc.communicate(prompt.encode())
    if proc.returncode != 0:
        raise RuntimeError(f"claude CLI failed (rc={proc.returncode}): {stderr.decode()[:200]}")
    return stdout.decode().strip()


def rewrite_narration_api(book_text: str) -> str:
    """Rewrite book text via Anthropic API (requires ANTHROPIC_API_KEY, billed separately)."""
    import anthropic

    client = anthropic.Anthropic()
    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1024,
        messages=[{"role": "user", "content": NARRATION_PROMPT.format(text=book_text)}],
    )
    return message.content[0].text.strip()


# ---------------------------------------------------------------------------
# TTS backends
# ---------------------------------------------------------------------------

async def generate_audio_edge_tts(text: str, path: str, voice: str = "zh-CN-XiaoxiaoNeural") -> bool:
    """Generate TTS audio via edge-tts."""
    import edge_tts

    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        communicate = edge_tts.Communicate(text, voice)
        await communicate.save(path)
        return True
    except Exception as e:
        print(f"    [TTS] Warning: edge-tts failed: {e}")
        return False


async def generate_audio_cosyvoice(text: str, path: str, base_url: str = "http://localhost:50000") -> bool:
    """Generate TTS audio via CosyVoice HTTP API."""
    import httpx

    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(f"{base_url}/tts", json={"text": text, "speaker": "中文女"})
            resp.raise_for_status()
        with open(path, "wb") as f:
            f.write(resp.content)
        return True
    except Exception as e:
        print(f"    [TTS] Warning: CosyVoice failed: {e}")
        return False


# ---------------------------------------------------------------------------
# Main processing
# ---------------------------------------------------------------------------

async def process_section(
    section_id: int,
    force: bool = False,
    dry_run: bool = False,
    tts_backend: str = "edge-tts",
    cosyvoice_url: str = "http://localhost:50000",
    voice: str = "zh-CN-XiaoxiaoNeural",
    rewriter: str = "cli",
    model: str = "sonnet",
    concurrency: int = 5,
):
    db = SessionLocal()
    try:
        section = db.query(TutorialSection).filter_by(id=section_id).first()
        if not section:
            print(f"Error: Section {section_id} not found")
            return

        book_slug = get_book_slug(db, section_id)
        audio_dir = REPO_ROOT / "data" / "tutorial_assets" / book_slug / "audio"
        audio_dir.mkdir(parents=True, exist_ok=True)

        figures = (
            db.query(TutorialFigure)
            .filter_by(section_id=section_id)
            .order_by(TutorialFigure.order)
            .all()
        )

        print(f"Section {section_id}: {section.title} — {len(figures)} figures")
        print(f"Rewriter: {rewriter} (model={model}), TTS: {tts_backend}, Concurrency: {concurrency}")
        print(f"Audio dir: {audio_dir}")
        print()

        # Collect figures needing work
        to_process = []
        for fig in figures:
            if not fig.book_text:
                print(f"  [{fig.figure_label}] ⏭ No book_text, skipping")
                continue
            if fig.narration and fig.audio_asset and not force:
                print(f"  [{fig.figure_label}] ✓ Already done")
                continue
            to_process.append(fig)

        if not to_process:
            print("\nAll figures already processed!")
            return

        print(f"\nProcessing {len(to_process)} figures...\n")

        sem = asyncio.Semaphore(concurrency)

        async def process_one(fig):
            """Process a single figure: narration + TTS."""
            async with sem:
                narration = None
                audio_asset = None

                # Step 1: Narration
                if fig.narration and not force:
                    narration = fig.narration
                    print(f"  [{fig.figure_label}] ✓ Existing narration")
                elif dry_run:
                    narration = f"[DRY RUN] Would rewrite: {fig.book_text[:50]}..."
                    print(f"  [{fig.figure_label}] {narration}")
                else:
                    print(f"  [{fig.figure_label}] Rewriting narration...")
                    try:
                        if rewriter == "cli":
                            narration = await rewrite_narration_cli(fig.book_text, model)
                        else:
                            narration = await asyncio.to_thread(rewrite_narration_api, fig.book_text)
                        print(f"  [{fig.figure_label}] ✓ Narration: {narration[:50]}...")
                    except Exception as e:
                        print(f"  [{fig.figure_label}] ✗ Narration failed: {e}, using book_text")
                        narration = fig.book_text

                # Step 2: TTS audio
                audio_filename = f"fig_{fig.id}.mp3"
                audio_path = audio_dir / audio_filename
                audio_asset_rel = f"tutorial_assets/{book_slug}/audio/{audio_filename}"

                if audio_path.exists() and not force:
                    audio_asset = audio_asset_rel
                    print(f"  [{fig.figure_label}] ✓ Audio exists: {audio_filename}")
                elif dry_run:
                    audio_asset = audio_asset_rel
                    print(f"  [{fig.figure_label}] [DRY RUN] Would generate: {audio_filename}")
                else:
                    print(f"  [{fig.figure_label}] Generating TTS → {audio_filename}")
                    if tts_backend == "cosyvoice":
                        ok = await generate_audio_cosyvoice(narration, str(audio_path), cosyvoice_url)
                    else:
                        ok = await generate_audio_edge_tts(narration, str(audio_path), voice)
                    if ok:
                        audio_asset = audio_asset_rel
                        print(f"  [{fig.figure_label}] ✓ Audio saved")
                    else:
                        print(f"  [{fig.figure_label}] ✗ Audio failed")

                return fig.id, narration, audio_asset

        results = await asyncio.gather(*[process_one(f) for f in to_process])

        # Step 3: Save all to DB
        if not dry_run:
            fig_map = {f.id: f for f in to_process}
            saved = 0
            for fig_id, narration, audio_asset in results:
                fig = fig_map[fig_id]
                if narration:
                    fig.narration = narration
                if audio_asset:
                    fig.audio_asset = audio_asset
                saved += 1
            db.commit()
            print(f"\n✓ Saved {saved} figures to DB")
        else:
            print(f"\n[DRY RUN] Would save {len(results)} figures")

        print("Done!")
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description="Generate voice narration for tutorial figures")
    parser.add_argument("--section-id", type=int, required=True, help="Section ID to process")
    parser.add_argument("--force", action="store_true", help="Re-generate even if narration/audio exists")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing")
    parser.add_argument("--tts", choices=["edge-tts", "cosyvoice"], default="edge-tts", help="TTS backend")
    parser.add_argument("--cosyvoice-url", default="http://localhost:50000", help="CosyVoice API URL")
    parser.add_argument("--voice", default="zh-CN-XiaoxiaoNeural", help="edge-tts voice name")
    parser.add_argument("--rewriter", choices=["cli", "api"], default="cli",
                        help="Narration rewriter: cli (claude CLI, Max subscription) or api (Anthropic API)")
    parser.add_argument("--model", default="sonnet", help="Model for claude CLI rewriter (default: sonnet)")
    parser.add_argument("--concurrency", type=int, default=5,
                        help="Max parallel narration+TTS tasks (default: 5)")
    args = parser.parse_args()

    asyncio.run(process_section(
        section_id=args.section_id,
        force=args.force,
        dry_run=args.dry_run,
        tts_backend=args.tts,
        cosyvoice_url=args.cosyvoice_url,
        voice=args.voice,
        rewriter=args.rewriter,
        model=args.model,
        concurrency=args.concurrency,
    ))


if __name__ == "__main__":
    main()
