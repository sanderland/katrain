#!/usr/bin/env python3
"""Generate tutorial lecture videos from figure data (board + narration + audio).

For each figure:
  1. Regenerate TTS audio with word-level timestamps via edge-tts SubMaker
  2. Parse move references from narration text (regex)
  3. Build a synchronized timeline (moves, subtitles, audio)
  4. Capture 3D board animation via Playwright video recording
  5. Post-process with ffmpeg (mix audio, encode MP4)

Usage:
    python scripts/generate_video.py --figure-id 1 --dry-run   # Preview timeline
    python scripts/generate_video.py --figure-id 1             # Generate one video
    python scripts/generate_video.py --section-id 1            # Generate all in section
"""

import argparse
import asyncio
import json
import os
import random
import re
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT))

from katrain.web.core.db import SessionLocal
from katrain.web.core.models_db import (
    TutorialBook,
    TutorialChapter,
    TutorialFigure,
    TutorialSection,
)

# ---------------------------------------------------------------------------
# Move reference parser (regex-based)
# ---------------------------------------------------------------------------

# Matches patterns like: 黑1, 黑棋的2位, 白棋3, 1位, 第1手, 第2步
MOVE_REF_PATTERN = re.compile(
    r"(?:黑棋?的?)(\d+)位?"  # 黑1, 黑棋的2位
    r"|(?:白棋?的?)(\d+)位?"  # 白1, 白棋的2位
    r"|(\d+)位"  # 1位, 2位
    r"|第(\d+)[手步]"  # 第1手, 第2步
)


def find_move_references(text: str) -> list[dict]:
    """Extract move number references from narration text.

    Returns list of {start_char, end_char, move_number} sorted by position.
    """
    refs = []
    for m in MOVE_REF_PATTERN.finditer(text):
        num = int(m.group(1) or m.group(2) or m.group(3) or m.group(4))
        refs.append({
            "start_char": m.start(),
            "end_char": m.end(),
            "move_number": num,
        })
    return refs


# ---------------------------------------------------------------------------
# Letter reference parser (e.g., "A方向", "A位", "A点", "A处", standalone "A")
# ---------------------------------------------------------------------------

LETTER_REF_PATTERN = re.compile(r"([A-Z])(?:这个)?(?:方向|位|点|处)?")


def find_letter_references(text: str) -> list[dict]:
    """Extract letter references from narration text (A, B, C, etc.).

    Returns list of {start_char, end_char, letter} sorted by position.
    """
    refs = []
    for m in LETTER_REF_PATTERN.finditer(text):
        refs.append({
            "start_char": m.start(),
            "end_char": m.end(),
            "letter": m.group(1),
        })
    return refs


# ---------------------------------------------------------------------------
# Subtitle segmenter
# ---------------------------------------------------------------------------

# Split at Chinese sentence-ending punctuation (keep delimiter with preceding text)
PUNCT_PATTERN = re.compile(r"([，。！？；：、])")


def split_subtitles(text: str, word_timings: list[dict]) -> list[dict]:
    """Split narration into subtitle segments at punctuation marks.

    Each segment maps to a time range from word_timings.
    Returns [{start_ms, end_ms, text, char_start, char_end}, ...].
    """
    # Build char→timing index: for each character position, find the word timing
    char_to_timing = {}
    running_char = 0
    for wt in word_timings:
        word_text = wt["text"]
        for i in range(len(word_text)):
            char_to_timing[running_char + i] = wt
        running_char += len(word_text)

    # Split text at punctuation
    parts = PUNCT_PATTERN.split(text)
    segments = []
    char_pos = 0

    i = 0
    while i < len(parts):
        segment_text = parts[i]
        # Attach the following punctuation if it exists
        if i + 1 < len(parts) and PUNCT_PATTERN.match(parts[i + 1]):
            segment_text += parts[i + 1]
            i += 2
        else:
            i += 1

        segment_text = segment_text.strip()
        if not segment_text:
            continue

        char_start = char_pos
        char_end = char_pos + len(segment_text)
        char_pos = char_end

        # Skip any whitespace/punctuation chars consumed but not in segment_text
        while char_pos < len(text) and text[char_pos] in " \n\t":
            char_pos += 1

        # Find timing for this segment
        start_ms = None
        end_ms = None

        for c in range(char_start, min(char_end, len(text))):
            if c in char_to_timing:
                wt = char_to_timing[c]
                t_start = wt["offset_ms"]
                t_end = wt["offset_ms"] + wt["duration_ms"]
                if start_ms is None or t_start < start_ms:
                    start_ms = t_start
                if end_ms is None or t_end > end_ms:
                    end_ms = t_end

        if start_ms is not None:
            segments.append({
                "start_ms": round(start_ms, 1),
                "end_ms": round(end_ms, 1),
                "text": segment_text,
                "char_start": char_start,
                "char_end": char_end,
            })

    return segments


# ---------------------------------------------------------------------------
# Edge-tts with word-level timing
# ---------------------------------------------------------------------------


async def generate_audio_with_timing(
    text: str, audio_path: str, voice: str = "zh-CN-XiaoxiaoNeural"
) -> list[dict]:
    """Generate TTS audio and return word-level timestamps.

    Returns [{offset_ms, duration_ms, text}, ...].
    Audio is saved to audio_path.
    """
    import edge_tts

    os.makedirs(os.path.dirname(audio_path), exist_ok=True)

    communicate = edge_tts.Communicate(text, voice, boundary="WordBoundary")
    submaker = edge_tts.SubMaker()
    word_timings = []

    with open(audio_path, "wb") as f:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                submaker.feed(chunk)
                word_timings.append({
                    "offset_ms": chunk["offset"] / 10_000,
                    "duration_ms": chunk["duration"] / 10_000,
                    "text": chunk["text"],
                })

    return word_timings


# ---------------------------------------------------------------------------
# Timeline builder
# ---------------------------------------------------------------------------


def get_book_slug(db, section_id: int) -> str:
    section = db.query(TutorialSection).filter_by(id=section_id).first()
    if not section:
        raise ValueError(f"Section {section_id} not found")
    chapter = db.query(TutorialChapter).filter_by(id=section.chapter_id).first()
    book = db.query(TutorialBook).filter_by(id=chapter.book_id).first()
    return book.slug


def parse_board_payload(figure) -> dict:
    bp = figure.board_payload
    if isinstance(bp, str):
        bp = json.loads(bp)
    return bp


def build_moves_list(bp: dict) -> list[dict]:
    """Extract ordered moves from board_payload (using labels for ordering).

    Returns [{number, color, pos}, ...] sorted by move number.
    """
    labels = bp.get("labels", {})
    stones_b = bp.get("stones", {}).get("B", [])
    stones_w = bp.get("stones", {}).get("W", [])

    # Build coordinate → (color, pos) map
    coord_map = {}
    for pos in stones_b:
        coord_map[f"{pos[0]},{pos[1]}"] = ("B", pos)
    for pos in stones_w:
        coord_map[f"{pos[0]},{pos[1]}"] = ("W", pos)

    moves = []
    for coord_key, label_val in labels.items():
        try:
            num = int(label_val)
        except (ValueError, TypeError):
            continue
        if coord_key in coord_map:
            color, pos = coord_map[coord_key]
            moves.append({"number": num, "color": color, "pos": pos})

    moves.sort(key=lambda m: m["number"])
    return moves


def build_initial_stones(bp: dict) -> list[dict]:
    """Extract stones without numeric labels (initial/setup stones).

    These are pre-placed on the board before any animated moves.
    Returns [{"color": "B"|"W", "pos": [col, row]}, ...]
    """
    labels = bp.get("labels", {})
    stones_b = bp.get("stones", {}).get("B", [])
    stones_w = bp.get("stones", {}).get("W", [])

    # Coordinates that have numeric labels are animated moves, not initial stones
    numeric_coords = set()
    for coord_key, label_val in labels.items():
        try:
            int(label_val)
            numeric_coords.add(coord_key)
        except (ValueError, TypeError):
            pass

    initial = []
    for pos in stones_b:
        if f"{pos[0]},{pos[1]}" not in numeric_coords:
            initial.append({"color": "B", "pos": pos})
    for pos in stones_w:
        if f"{pos[0]},{pos[1]}" not in numeric_coords:
            initial.append({"color": "W", "pos": pos})

    return initial


def build_letters(bp: dict) -> list[dict]:
    """Extract letter annotations from board_payload (on empty intersections).

    Returns [{"letter": "A", "pos": [col, row]}, ...]
    """
    letters = bp.get("letters", {})
    result = []
    for coord_key, letter in letters.items():
        col, row = map(int, coord_key.split(","))
        result.append({"letter": letter, "pos": [col, row]})
    return result


def build_timeline(
    figure,
    word_timings: list[dict],
    subtitles: list[dict],
    move_refs: list[dict],
    bp: dict,
    port: int = 8001,
    polar_angle: float = 0.15,
) -> dict:
    """Build the complete timeline JSON for video recording.

    Matches move references to word timings to determine when each stone should drop.
    """
    moves = build_moves_list(bp)
    initial_stones = build_initial_stones(bp)
    narration = figure.narration

    # Map move number → trigger time from narration
    # For each move_ref, find which word_timing contains it
    char_to_timing = {}
    running_char = 0
    for wt in word_timings:
        for i in range(len(wt["text"])):
            char_to_timing[running_char + i] = wt
        running_char += len(wt["text"])

    move_trigger_map = {}
    for ref in move_refs:
        mid_char = (ref["start_char"] + ref["end_char"]) // 2
        if mid_char in char_to_timing:
            wt = char_to_timing[mid_char]
            move_trigger_map[ref["move_number"]] = round(wt["offset_ms"], 1)

    # Get total audio duration from last word timing
    if word_timings:
        last_wt = word_timings[-1]
        audio_end_ms = round(last_wt["offset_ms"] + last_wt["duration_ms"], 1)
    else:
        audio_end_ms = 5000

    # Assign trigger times to moves — enforcing sequential order.
    # Moves must always play in ascending number order with at least 1s gap.
    # When narration mentions move N, all moves up to N play in sequence.
    MOVE_INTERVAL_MS = 1000
    prev_trigger = 0
    for move in moves:  # already sorted by number
        if move["number"] in move_trigger_map:
            # Narration-matched: use narration time, but never before prev + interval
            move["trigger_ms"] = max(move_trigger_map[move["number"]], prev_trigger + MOVE_INTERVAL_MS)
        else:
            # Unmatched: play 1s after previous move
            move["trigger_ms"] = prev_trigger + MOVE_INTERVAL_MS
        prev_trigger = move["trigger_ms"]

    # Calculate total duration: max of audio end and last move trigger + buffer
    last_move_time = max((m["trigger_ms"] for m in moves), default=0)
    total_duration_ms = max(audio_end_ms, last_move_time + 1000) + 2000  # 2s buffer at end

    # Build letter annotations with trigger times
    letters = build_letters(bp)
    if letters:
        letter_refs = find_letter_references(narration)
        for letter_entry in letters:
            # Find matching reference in narration
            matched = False
            for ref in letter_refs:
                if ref["letter"] == letter_entry["letter"]:
                    mid_char = (ref["start_char"] + ref["end_char"]) // 2
                    if mid_char in char_to_timing:
                        wt = char_to_timing[mid_char]
                        letter_entry["trigger_ms"] = round(wt["offset_ms"], 1)
                        matched = True
                        break
            if not matched:
                # Show unmatched letters after all moves are placed
                letter_entry["trigger_ms"] = last_move_time + 1000

    # Calculate total duration: max of audio end and last move/letter trigger + buffer
    last_letter_time = max((lt["trigger_ms"] for lt in letters), default=0) if letters else 0
    total_duration_ms = max(audio_end_ms, last_move_time + 1000, last_letter_time + 1000) + 2000

    # Build audio URL for the recording page to play
    audio_asset = figure.audio_asset or ""
    audio_url = f"/api/v1/tutorials/assets/{audio_asset}" if audio_asset else ""

    return {
        "figure_id": figure.id,
        "figure_label": figure.figure_label,
        "board_size": bp.get("size", 19),
        "viewport": bp.get("viewport"),
        "initial_stones": initial_stones,
        "moves": moves,
        "letters": letters,
        "subtitles": subtitles,
        "total_duration_ms": round(total_duration_ms),
        "audio_url": audio_url,
        "polar_angle": polar_angle,
    }


# ---------------------------------------------------------------------------
# Playwright video capture
# ---------------------------------------------------------------------------


def build_frame_schedule(timeline: dict, base_fps: int = 5, drop_fps: int = 24) -> list[float]:
    """Build adaptive frame schedule: base_fps normally, drop_fps during stone drops.

    Returns sorted list of frame times (ms) with higher density around move triggers
    for smooth drop animations.
    """
    duration_ms = timeline["total_duration_ms"]
    base_interval = 1000.0 / base_fps
    drop_interval = 1000.0 / drop_fps
    drop_window_ms = 700  # capture at high fps for 700ms after each drop

    # Collect high-fps windows around each move trigger
    drop_windows = []  # [(start_ms, end_ms), ...]
    for move in timeline.get("moves", []):
        t = move["trigger_ms"]
        drop_windows.append((t, t + drop_window_ms))

    # Merge overlapping windows
    drop_windows.sort()
    merged = []
    for start, end in drop_windows:
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))

    def in_drop_window(t: float) -> bool:
        for start, end in merged:
            if start <= t <= end:
                return True
        return False

    # Build frame times
    frames = set()
    t = 0.0
    while t <= duration_ms:
        frames.add(round(t, 1))
        if in_drop_window(t):
            t += drop_interval
        else:
            t += base_interval

    # Ensure all drop window boundaries are included
    for start, end in merged:
        t = start
        while t <= end:
            frames.add(round(t, 1))
            t += drop_interval

    return sorted(frames)


async def capture_video(timeline: dict, port: int, output_dir: str, fps: int = 5) -> str:
    """Capture 3D board animation with adaptive framerate.

    Uses base_fps (5) for static periods and 24fps during stone drop animations
    for smooth visual effect. Stitches with ffmpeg concat demuxer for variable
    frame durations.
    """
    from playwright.async_api import async_playwright

    frames_dir = Path(output_dir) / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)

    frame_schedule = build_frame_schedule(timeline, base_fps=fps, drop_fps=24)

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--use-gl=angle",
                "--use-angle=swiftshader",
                "--no-sandbox",
            ],
        )
        context = await browser.new_context(
            viewport={"width": 2560, "height": 1440},
        )
        # Intercept external CDN requests (troika font resolver stubs)
        async def _stub_external(route):
            url = route.request.url
            if "codepoint-index" in url:
                await route.fulfill(status=200, body="[1, {}]", content_type="application/json")
            elif "font-meta" in url:
                await route.fulfill(
                    status=200,
                    body='{"id":"noto-sans","typeforms":{"sans-serif":{"normal":{"400":true}}}}',
                    content_type="application/json",
                )
            elif "font-files" in url:
                await route.fulfill(status=404, body="", content_type="application/octet-stream")
            elif "fonts.googleapis.com" in url:
                await route.fulfill(status=200, body="/* stub */", content_type="text/css")
            else:
                await route.fulfill(status=200, body="{}", content_type="application/json")

        await context.route("**/*fonts.googleapis.com/**", _stub_external)
        await context.route("**/*cdn.jsdelivr.net/**", _stub_external)
        await context.route("**/*fonts.gstatic.com/**", _stub_external)

        page = await context.new_page()

        # Capture console errors for debugging
        page.on("console", lambda msg: print(f"    [browser {msg.type}] {msg.text}") if msg.type in ("error", "warning") else None)

        await page.goto(f"http://localhost:{port}/record", wait_until="networkidle")

        # Inject timeline data and trigger initialization
        await page.evaluate(f"window.__RECORDING_DATA = {json.dumps(timeline)}")
        await page.evaluate('window.dispatchEvent(new Event("startRecording"))')

        # Wait for Three.js to initialize (board rendering warmup)
        print("  Waiting for Three.js initialization...")
        await page.wait_for_timeout(5000)
        await page.wait_for_function("window.__RECORDING_READY === true", timeout=10000)

        # Preload troika font: show all moves briefly to trigger font loading + SDF generation,
        # then reset. Without this, the async font load wouldn't complete within frame windows.
        print("  Preloading 3D text font...")
        await page.evaluate(f"window.__setFrame({timeline['total_duration_ms']})")
        await page.evaluate("window.__forceRender && window.__forceRender()")
        await page.wait_for_timeout(3000)
        # Reset to frame 0 (initial stones only)
        await page.evaluate("window.__setFrame(0)")
        await page.evaluate("window.__forceRender && window.__forceRender()")
        await page.wait_for_timeout(500)

        # Capture frames with adaptive framerate
        total_frames = len(frame_schedule)
        duration_ms = timeline["total_duration_ms"]
        print(f"  Capturing {total_frames} frames ({duration_ms/1000:.1f}s, adaptive {fps}/24fps)...")

        for i, t_ms in enumerate(frame_schedule):
            await page.evaluate(f"window.__setFrame({t_ms})")
            await page.evaluate("window.__forceRender && window.__forceRender()")
            await page.wait_for_timeout(200)
            frame_path = frames_dir / f"frame_{i:05d}.png"
            await page.screenshot(path=str(frame_path))

            if (i + 1) % 50 == 0:
                print(f"    Frame {i+1}/{total_frames} (t={t_ms/1000:.1f}s)")

        await context.close()
        await browser.close()

    # Build ffmpeg concat file with per-frame duration
    concat_file = str(Path(output_dir) / "frames.txt")
    with open(concat_file, "w") as f:
        for i in range(len(frame_schedule)):
            frame_path = str(frames_dir / f"frame_{i:05d}.png")
            if i + 1 < len(frame_schedule):
                duration = (frame_schedule[i + 1] - frame_schedule[i]) / 1000.0
            else:
                duration = 1.0 / fps  # last frame: use base interval
            f.write(f"file '{frame_path}'\n")
            f.write(f"duration {duration:.6f}\n")
        # ffmpeg concat requires last file repeated without duration
        f.write(f"file '{frames_dir / f'frame_{len(frame_schedule)-1:05d}.png'}'\n")

    # Stitch frames into video
    video_path = str(Path(output_dir) / "raw_video.mp4")
    cmd = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", concat_file,
        "-c:v", "libx264", "-preset", "medium", "-crf", "18",
        "-pix_fmt", "yuv420p",
        "-vsync", "vfr",
        video_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  ffmpeg stitch stderr: {result.stderr[-500:]}")
        raise RuntimeError(f"ffmpeg frame stitching failed (rc={result.returncode})")

    return video_path


# ---------------------------------------------------------------------------
# ffmpeg audio mixing + video composition
# ---------------------------------------------------------------------------

STONE_SOUNDS_DIR = REPO_ROOT / "katrain" / "sounds"


def mix_audio(narration_path: str, moves: list[dict], output_path: str):
    """Mix narration audio with stone placement sounds at trigger times."""
    if not moves:
        # No moves — just copy narration
        subprocess.run(
            ["ffmpeg", "-y", "-i", narration_path, "-c:a", "aac", "-b:a", "192k", output_path],
            check=True,
            capture_output=True,
        )
        return

    inputs = ["-i", narration_path]
    filter_parts = []

    for i, move in enumerate(moves):
        stone_idx = random.randint(1, 5)
        stone_file = str(STONE_SOUNDS_DIR / f"stone{stone_idx}.wav")
        inputs.extend(["-i", stone_file])
        # Add 500ms delay for stone "landing" (drop animation takes ~0.5s)
        delay_ms = int(move["trigger_ms"]) + 500
        filter_parts.append(f"[{i + 1}:a]adelay={delay_ms}|{delay_ms},volume=0.6[s{i}]")

    # Mix all stone sounds together
    stone_labels = "".join(f"[s{i}]" for i in range(len(moves)))
    if len(moves) == 1:
        filter_parts.append(f"{stone_labels}acopy[stones]")
    else:
        filter_parts.append(
            f"{stone_labels}amix=inputs={len(moves)}:normalize=0[stones]"
        )

    # Mix narration with stone sounds
    filter_parts.append(
        "[0:a][stones]amix=inputs=2:weights=1 0.4:normalize=0[out]"
    )

    filter_complex = ";".join(filter_parts)

    cmd = [
        "ffmpeg", "-y",
        *inputs,
        "-filter_complex", filter_complex,
        "-map", "[out]",
        "-c:a", "aac", "-b:a", "192k",
        output_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  ffmpeg mix_audio stderr: {result.stderr[-500:]}")
        raise RuntimeError(f"ffmpeg audio mix failed (rc={result.returncode})")


def compose_final_video(raw_video_path: str, mixed_audio_path: str, output_path: str):
    """Merge video with mixed audio into final MP4."""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    cmd = [
        "ffmpeg", "-y",
        "-i", raw_video_path,
        "-i", mixed_audio_path,
        "-map", "0:v",
        "-map", "1:a",
        "-c:v", "copy",
        "-c:a", "copy",
        "-movflags", "+faststart",
        "-shortest",
        output_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  ffmpeg compose stderr: {result.stderr[-500:]}")
        raise RuntimeError(f"ffmpeg compose failed (rc={result.returncode})")


# ---------------------------------------------------------------------------
# Main processing
# ---------------------------------------------------------------------------


async def process_figure(
    figure_id: int,
    port: int = 8001,
    voice: str = "zh-CN-XiaoxiaoNeural",
    dry_run: bool = False,
    force: bool = False,
    polar_angle: float = 0.15,
):
    """Process a single figure: build timeline, capture video, compose MP4."""
    db = SessionLocal()
    try:
        figure = db.query(TutorialFigure).filter_by(id=figure_id).first()
        if not figure:
            print(f"Error: Figure {figure_id} not found")
            return

        if not figure.narration:
            print(f"Error: Figure {figure_id} has no narration. Run generate_voice.py first.")
            return

        book_slug = get_book_slug(db, figure.section_id)
        bp = parse_board_payload(figure)

        print(f"Figure {figure_id} ({figure.figure_label})")
        print(f"  Narration: {figure.narration[:60]}...")
        print(f"  Stones: B={len(bp['stones'].get('B', []))}, W={len(bp['stones'].get('W', []))}")
        initial = build_initial_stones(bp)
        print(f"  Initial (setup) stones: {len(initial)}, Labeled moves: {len(build_moves_list(bp))}")

        # Check if video already exists
        video_dir = REPO_ROOT / "data" / "tutorial_assets" / book_slug / "video"
        video_path = video_dir / f"fig_{figure_id}.mp4"
        if video_path.exists() and not force:
            print(f"  Video already exists: {video_path}")
            return

        # Step 1: Generate audio with timing
        print("  Step 1: Generating audio with word-level timing...")
        timing_audio_dir = REPO_ROOT / "data" / "tutorial_assets" / book_slug / "audio"
        timing_audio_path = str(timing_audio_dir / f"fig_{figure_id}.mp3")
        word_timings = await generate_audio_with_timing(
            figure.narration, timing_audio_path, voice
        )
        print(f"    Got {len(word_timings)} word timings")

        # Step 2: Parse move references
        move_refs = find_move_references(figure.narration)
        print(f"    Found {len(move_refs)} move references: {move_refs}")

        # Step 3: Build subtitles
        subtitles = split_subtitles(figure.narration, word_timings)
        print(f"    Split into {len(subtitles)} subtitle segments")

        # Step 4: Build timeline
        timeline = build_timeline(figure, word_timings, subtitles, move_refs, bp, port, polar_angle)

        if dry_run:
            print("\n=== Timeline JSON ===")
            print(json.dumps(timeline, ensure_ascii=False, indent=2))
            return

        # Step 5: Capture video via Playwright
        print("  Step 5: Capturing video via Playwright...")
        with tempfile.TemporaryDirectory(prefix="katrain_video_") as tmpdir:
            webm_path = await capture_video(timeline, port, tmpdir)
            print(f"    Recorded: {webm_path}")

            # Step 6: Mix audio
            print("  Step 6: Mixing audio (narration + stone sounds)...")
            mixed_audio_path = os.path.join(tmpdir, "mixed_audio.m4a")
            mix_audio(timing_audio_path, timeline["moves"], mixed_audio_path)

            # Step 7: Compose final video
            print("  Step 7: Composing final MP4...")
            compose_final_video(webm_path, mixed_audio_path, str(video_path))

        print(f"  Done! Video saved to: {video_path}")
        file_size = video_path.stat().st_size / 1024 / 1024
        print(f"  File size: {file_size:.1f} MB")

    finally:
        db.close()


async def process_section(section_id: int, concurrency: int = 1, **kwargs):
    """Process all figures in a section, optionally in parallel."""
    db = SessionLocal()
    try:
        figures = (
            db.query(TutorialFigure)
            .filter_by(section_id=section_id)
            .order_by(TutorialFigure.order)
            .all()
        )
        figure_ids = [f.id for f in figures if f.narration and f.audio_asset]
        print(f"Section {section_id}: {len(figure_ids)} figures with narration (concurrency={concurrency})")
    finally:
        db.close()

    if concurrency <= 1:
        for fid in figure_ids:
            await process_figure(fid, **kwargs)
            print()
    else:
        sem = asyncio.Semaphore(concurrency)

        async def process_one(fid):
            async with sem:
                await process_figure(fid, **kwargs)

        await asyncio.gather(*[process_one(fid) for fid in figure_ids])


# ---------------------------------------------------------------------------
# Section video concatenation (Phase 2)
# ---------------------------------------------------------------------------


def generate_title_card(
    text: str, output_path: str, duration: float = 2.0,
    width: int = 2560, height: int = 1440, fps: int = 5,
):
    """Generate a title card video (white text on dark background).

    Uses Pillow for the image, then ffmpeg to create a video from it.
    """
    from PIL import Image, ImageDraw, ImageFont

    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    # Create title card image
    img = Image.new("RGB", (width, height), color=(15, 15, 15))
    draw = ImageDraw.Draw(img)

    # Try to find a CJK font
    font = None
    font_paths = [
        "/System/Library/Fonts/STHeiti Medium.ttc",  # macOS
        "/System/Library/Fonts/PingFang.ttc",  # macOS
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",  # Linux
        "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",  # Linux alt
    ]
    for fp in font_paths:
        if os.path.exists(fp):
            try:
                font = ImageFont.truetype(fp, 56)
                break
            except Exception:
                continue
    if font is None:
        font = ImageFont.load_default()

    # Center the text
    bbox = draw.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    x = (width - text_w) // 2
    y = (height - text_h) // 2
    draw.text((x, y), text, fill="white", font=font)

    # Save as PNG
    img_path = output_path.replace(".mp4", ".png")
    img.save(img_path)

    # Convert to video with silent audio
    cmd = [
        "ffmpeg", "-y",
        "-loop", "1", "-i", img_path,
        "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono",
        "-t", str(duration),
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-c:a", "aac", "-b:a", "64k",
        "-pix_fmt", "yuv420p",
        "-r", str(fps),
        "-shortest",
        output_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  ffmpeg title card stderr: {result.stderr[-500:]}")
        raise RuntimeError(f"ffmpeg title card failed (rc={result.returncode})")


def concat_section_video(section_id: int, force: bool = False):
    """Concatenate all figure videos in a section with title cards and fade transitions."""
    db = SessionLocal()
    try:
        section = db.query(TutorialSection).filter_by(id=section_id).first()
        if not section:
            print(f"Error: Section {section_id} not found")
            return

        chapter = db.query(TutorialChapter).filter_by(id=section.chapter_id).first()
        book = db.query(TutorialBook).filter_by(id=chapter.book_id).first()
        book_slug = book.slug

        figures = (
            db.query(TutorialFigure)
            .filter_by(section_id=section_id)
            .order_by(TutorialFigure.order)
            .all()
        )
    finally:
        db.close()

    video_dir = REPO_ROOT / "data" / "tutorial_assets" / book_slug / "video"
    output_path = video_dir / f"section_{section_id}.mp4"

    if output_path.exists() and not force:
        print(f"Section video already exists: {output_path}")
        return

    # Collect figure videos that exist
    fig_videos = []
    for fig in figures:
        fig_path = video_dir / f"fig_{fig.id}.mp4"
        if fig_path.exists():
            fig_videos.append((fig, fig_path))

    if not fig_videos:
        print(f"No figure videos found for section {section_id}")
        return

    total = len(fig_videos)
    print(f"Section {section_id}: {section.title} — concatenating {total} figure videos")

    with tempfile.TemporaryDirectory(prefix="katrain_section_") as tmpdir:
        # Build list of segments: [section_title, fig_title, fig_video, fig_title, fig_video, ...]
        segments = []

        # Section title card at the very beginning
        section_title = f"{section.section_number}. {section.title}"
        section_title_path = os.path.join(tmpdir, "section_title.mp4")
        print(f"  Generating section title card: {section_title}")
        generate_title_card(section_title, section_title_path, duration=3.0)
        segments.append(section_title_path)

        for idx, (fig, fig_path) in enumerate(fig_videos):
            # Generate title card for this figure
            label = f"{fig.figure_label} ({idx + 1}/{total})"
            title_path = os.path.join(tmpdir, f"title_{idx:03d}.mp4")
            print(f"  Generating title card: {label}")
            generate_title_card(label, title_path)
            segments.append(title_path)
            segments.append(str(fig_path))

        # Write ffmpeg concat list
        # Use intermediate re-encoded segments to ensure uniform encoding
        normalized = []
        for i, seg_path in enumerate(segments):
            norm_path = os.path.join(tmpdir, f"norm_{i:03d}.mp4")
            cmd = [
                "ffmpeg", "-y", "-i", seg_path,
                "-c:v", "libx264", "-preset", "fast", "-crf", "18",
                "-c:a", "aac", "-b:a", "128k", "-ar", "24000", "-ac", "1",
                "-pix_fmt", "yuv420p",
                "-r", "5",  # uniform frame rate
                "-s", "2560x1440",  # uniform resolution
                norm_path,
            ]
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                print(f"  ffmpeg normalize stderr: {result.stderr[-300:]}")
                raise RuntimeError(f"ffmpeg normalize failed for segment {i}")
            normalized.append(norm_path)

        # Write concat file
        concat_file = os.path.join(tmpdir, "concat.txt")
        with open(concat_file, "w") as f:
            for norm_path in normalized:
                f.write(f"file '{norm_path}'\n")

        # Concatenate all segments
        print(f"  Concatenating {len(normalized)} segments...")
        os.makedirs(os.path.dirname(str(output_path)), exist_ok=True)
        cmd = [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0",
            "-i", concat_file,
            "-c:v", "libx264", "-preset", "medium", "-crf", "18",
            "-c:a", "aac", "-b:a", "128k",
            "-movflags", "+faststart",
            str(output_path),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"  ffmpeg concat stderr: {result.stderr[-500:]}")
            raise RuntimeError(f"ffmpeg concat failed (rc={result.returncode})")

    file_size = output_path.stat().st_size / 1024 / 1024
    print(f"  Done! Section video: {output_path} ({file_size:.1f} MB)")


def main():
    parser = argparse.ArgumentParser(
        description="Generate tutorial lecture videos from figure data"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--figure-id", type=int, help="Process a single figure")
    group.add_argument("--section-id", type=int, help="Process all figures in a section")
    group.add_argument("--section-video", type=int, metavar="SECTION_ID",
                       help="Concatenate existing figure videos into a section video")

    parser.add_argument("--port", type=int, default=8001, help="Web UI port (default: 8001)")
    parser.add_argument("--voice", default="zh-CN-XiaoxiaoNeural", help="edge-tts voice")
    parser.add_argument("--dry-run", action="store_true", help="Preview timeline only")
    parser.add_argument("--force", action="store_true", help="Regenerate even if video exists")
    parser.add_argument(
        "--polar-angle", type=float, default=0.15,
        help="Camera tilt as fraction of pi (0.05=bird's eye, 0.38=most tilted, default: 0.15)"
    )
    parser.add_argument(
        "--concurrency", type=int, default=1,
        help="Parallel figure processing for --section-id (default: 1)"
    )

    args = parser.parse_args()

    if args.figure_id:
        asyncio.run(process_figure(
            figure_id=args.figure_id,
            port=args.port,
            voice=args.voice,
            dry_run=args.dry_run,
            force=args.force,
            polar_angle=args.polar_angle,
        ))
    elif args.section_video:
        concat_section_video(
            section_id=args.section_video,
            force=args.force,
        )
    else:
        asyncio.run(process_section(
            section_id=args.section_id,
            concurrency=args.concurrency,
            port=args.port,
            voice=args.voice,
            dry_run=args.dry_run,
            force=args.force,
            polar_angle=args.polar_angle,
        ))


if __name__ == "__main__":
    main()
