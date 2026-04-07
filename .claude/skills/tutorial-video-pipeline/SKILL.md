---
name: tutorial-video-pipeline
description: Use when generating tutorial lecture videos from figure data, creating section-level concatenated videos, or troubleshooting video generation. Triggers on video generation, 生成视频, generate_video, tutorial video, section video, 视频讲解.
---

# Tutorial Video Pipeline

Generate Go tutorial lecture videos by composing 3D board animation, synchronized subtitles, and voice narration into MP4 files.

## Execution Workflow

When the user asks to generate videos for a section (e.g., "为 Section 1 生成视频"), follow this exact sequence:

### Step 1: Verify prerequisites

```bash
# Check web server is running
curl -s -o /dev/null -w "%{http_code}" http://localhost:8001/health
```

If not 200, start it:
```bash
python -m katrain --ui web --port 8001 &
sleep 20  # Wait for build + startup
```

Also verify figures have narration:
```python
python3 -c "
import sys; sys.path.insert(0, '.')
from katrain.web.core.db import SessionLocal
from katrain.web.core.models_db import TutorialFigure
db = SessionLocal()
figs = db.query(TutorialFigure).filter_by(section_id=SECTION_ID).all()
ready = sum(1 for f in figs if f.narration and f.audio_asset)
print(f'{ready}/{len(figs)} figures ready')
db.close()
"
```

If not all ready, run `tutorial-voice-pipeline` first.

### Step 2: Generate all figure videos (with concurrency)

Choose concurrency based on machine:
- Macbook: `--concurrency 2`
- Server (192 cores): `--concurrency 20`

```bash
PYTHONUNBUFFERED=1 python scripts/generate_video.py \
  --section-id SECTION_ID \
  --concurrency N \
  --force \
  > /tmp/video_section_SECTION_ID.log 2>&1
```

**Monitor progress** by tailing the log:
```bash
tail -f /tmp/video_section_SECTION_ID.log
```

**Verify completion**: check all figure videos exist:
```bash
ls -la data/tutorial_assets/*/video/fig_*.mp4 | wc -l
```

### Step 3: Generate section video

After ALL figure videos are complete:

```bash
python scripts/generate_video.py --section-video SECTION_ID --force
```

This creates: `data/tutorial_assets/{slug}/video/section_{SECTION_ID}.mp4`

Structure: Section title card (3s) → 图1 title (2s) → 图1 video → 图2 title (2s) → 图2 video → ...

### Step 4: Verify video files and DB records

```bash
# Check output files
ls -lh data/tutorial_assets/*/video/section_SECTION_ID.mp4

# Check duration
ffprobe -v quiet -show_entries format=duration \
  -of default=noprint_wrappers=1:nokey=1 \
  data/tutorial_assets/*/video/section_SECTION_ID.mp4
```

Verify DB records were written (step 2 auto-writes these):
```bash
python3 -c "
import sys; sys.path.insert(0, '.')
from katrain.web.core.db import SessionLocal
from katrain.web.core.models_db import TutorialFigure
db = SessionLocal()
figs = db.query(TutorialFigure).filter_by(section_id=SECTION_ID).all()
for f in figs:
    status = 'OK' if f.video_asset else 'MISSING'
    print(f'  fig {f.id}: {status}  asset={f.video_asset}  size={f.video_size_bytes}  duration_ms={f.video_duration_ms}')
db.close()
"
```

### Processing multiple sections

For multiple sections, process them sequentially (each section = steps 2-3):

```bash
for sid in 1 2 3; do
  echo "=== Section $sid ==="
  python scripts/generate_video.py --section-id $sid --concurrency 2 --force
  python scripts/generate_video.py --section-video $sid --force
done
```

## DB Metadata Management

### Auto-write on generation

`generate_video.py` automatically writes video metadata to the DB after each figure video is generated. No manual step needed — step 2 handles this:

| DB Field | Value | When Written |
|----------|-------|-------------|
| `video_asset` | `tutorial_assets/{slug}/video/fig_{id}.mp4` | After compose (step 2 with `--force`) |
| `video_duration_ms` | Timeline total duration | After compose (step 2 with `--force`) |
| `video_size_bytes` | Output file size | After compose (step 2 with `--force`) |

When running **without** `--force` on an existing video, the script auto-backfills `video_asset` and `video_size_bytes` if they are NULL (but skips `video_duration_ms` since it requires regeneration).

### Production DB migration (first-time setup)

When deploying the video fields to a production PostgreSQL database for the first time, the columns must be added **before** restarting the app (SQLAlchemy will crash on SELECT if columns are missing):

```bash
# Run migration on production DB
docker exec -i katrain-postgres psql -U katrain_user -d katrain_db \
  -f - < scripts/migrate_video_fields.sql

# Verify columns
docker exec katrain-postgres psql -U katrain_user -d katrain_db \
  -c "\d tutorial_figures" | grep video
```

Migration script: `scripts/migrate_video_fields.sql` (uses `IF NOT EXISTS`, safe to re-run).

### Backfill existing videos to DB

For videos already on disk but missing DB records (e.g., after first migration), run inside the Docker container:

```bash
docker exec katrain-web python -c "
from katrain.web.core.db import SessionLocal
from katrain.web.core.models_db import TutorialFigure
from pathlib import Path

db = SessionLocal()
REPO = Path('/app')

figures = db.query(TutorialFigure).filter(
    TutorialFigure.audio_asset.isnot(None),
    TutorialFigure.video_asset.is_(None)
).all()

updated = 0
for fig in figures:
    parts = fig.audio_asset.split('/')
    if len(parts) < 2:
        continue
    book_slug = parts[1]
    video_path = REPO / 'data' / 'tutorial_assets' / book_slug / 'video' / f'fig_{fig.id}.mp4'
    if video_path.exists():
        fig.video_asset = f'tutorial_assets/{book_slug}/video/fig_{fig.id}.mp4'
        fig.video_size_bytes = video_path.stat().st_size
        updated += 1

db.commit()
db.close()
print(f'Backfilled {updated} figures')
"
```

Alternatively, run **without** `--force` on a section to trigger per-figure backfill:
```bash
python scripts/generate_video.py --section-id SECTION_ID
```

## CLI Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `--figure-id ID` | — | Process single figure |
| `--section-id ID` | — | Process all figures in section |
| `--section-video ID` | — | Concatenate figure videos into section video |
| `--port PORT` | 8001 | Web UI server port |
| `--polar-angle F` | 0.15 | Camera tilt (0.05=bird's eye, 0.38=flat side view) |
| `--voice NAME` | zh-CN-XiaoxiaoNeural | edge-tts voice |
| `--force` | false | Regenerate even if video exists |
| `--dry-run` | false | Preview timeline JSON only |
| `--concurrency N` | 1 | Parallel figure processing (for --section-id) |

## Pipeline Execution Order

This skill is step 3 in the tutorial digitization pipeline:

| Order | Skill | Script | Prerequisite |
|-------|-------|--------|-------------|
| 0 | `tutorial-book-import` | `import_book.py` | book.json + pages |
| 1 | `tutorial-recognition-pipeline` | `recognize_boards_v2.py` | Figures with page_image_path |
| 2 | `tutorial-voice-pipeline` | `generate_voice.py` | Figures with book_text |
| **3** | **`tutorial-video-pipeline`** | **`generate_video.py`** | **Figures with narration + audio_asset** |

## Architecture

```
Per-figure pipeline:
  1. Load figure from DB (board_payload, narration, audio_asset)
  2. Generate audio with word-level timestamps (edge-tts SubMaker, boundary=WordBoundary)
  3. Parse move references from narration (regex: 黑1, 白2位, 第N手)
  4. Build timeline JSON (moves + subtitles split at Chinese punctuation)
  5. Capture frames via Playwright (deterministic __setFrame API, 5fps)
  6. Mix audio: narration + stone sounds (ffmpeg adelay + amix)
  7. Compose: raw frames + mixed audio → fig_{id}.mp4
  8. Poster thumbnail: ffmpeg extracts frame at ~5s → fig_{id}.jpg
  9. Write DB: video_asset, video_duration_ms, video_size_bytes → TutorialFigure

Section video pipeline:
  1. Section title card "N. 标题" (Pillow + ffmpeg, 3s)
  2. For each figure: title card "图N (i/total)" (2s) + figure video
  3. Normalize all segments (uniform 2560x1440, 5fps, H.264, AAC)
  4. ffmpeg concat → section_{id}.mp4
  5. Poster thumbnail: ffmpeg extracts frame at 5s → section_{id}.jpg
```

## Output Files

- Per-figure: `data/tutorial_assets/{book_slug}/video/fig_{figure_id}.mp4`
- Per-figure poster: `data/tutorial_assets/{book_slug}/video/fig_{figure_id}.jpg`
- Per-section: `data/tutorial_assets/{book_slug}/video/section_{section_id}.mp4`
- Per-section poster: `data/tutorial_assets/{book_slug}/video/section_{section_id}.jpg`
- Resolution: 2560x1440 (2K), H.264, 5fps, AAC audio
- Poster: JPG, ~150-200KB, single frame extracted at ~5s
- Served via existing `/api/v1/tutorials/assets/` endpoint

## Frontend Integration

- **TutorialFigurePage**: video player below narration (column 3), auto-hides if no video. Uses `<video poster=...>` with JPG derived from `video_asset` by convention (`.mp4` → `.jpg`).
- **TutorialBookDetailPage**: play icon left of section title (driven by `has_video` field from sections API), opens fullscreen dialog with poster.
- Poster convention: no DB field needed — frontend replaces `.mp4` with `.jpg` in the asset URL.

### Backfill poster thumbnails for existing videos

If videos were generated before poster support was added:

```bash
cd data/tutorial_assets/{book_slug}/video
for mp4 in fig_*.mp4 section_*.mp4; do
  jpg="${mp4%.mp4}.jpg"
  [ -f "$jpg" ] || ffmpeg -y -ss 5 -i "$mp4" -vframes 1 -q:v 2 "$jpg" 2>/dev/null
done
```

## Common Issues

| Issue | Fix |
|-------|-----|
| Board not rendering | Increase warmup (default 5s) or check `--use-gl=angle` flag |
| Camera angle wrong | StaticCamera is used for recording; adjust `--polar-angle` |
| Stones not appearing | Ensure 300ms+ wait after `__setFrame()` for React re-render |
| ffmpeg drawtext missing | Uses Pillow for title cards (no drawtext dependency) |
| Audio out of sync | Audio is regenerated with timing each run; don't skip step 2 |
| Generation too slow | Increase `--concurrency`; use server with more CPU cores |
