---
name: tutorial-video-pipeline
description: Use when generating tutorial lecture videos from figure data, creating section-level concatenated videos, or troubleshooting video generation. Triggers on video generation, 生成视频, generate_video, tutorial video, section video, 视频讲解.
---

# Tutorial Video Pipeline

Generate Go tutorial lecture videos by composing 3D board animation, synchronized subtitles, and voice narration into MP4 files.

## Prerequisites

- Web UI server running: `python -m katrain --ui web --port 8001`
- Figures must have `narration` and `audio_asset` (run `generate_voice.py` first)
- System deps: `ffmpeg`, `playwright install chromium`, `Pillow`

## Pipeline Execution Order

| Order | Skill | Script | Prerequisite |
|-------|-------|--------|-------------|
| 0 | `tutorial-book-import` | `import_book.py` | book.json + pages |
| 1 | `tutorial-recognition-pipeline` | `recognize_boards_v2.py` | Figures with page_image_path |
| 2 | `tutorial-voice-pipeline` | `generate_voice.py` | Figures with book_text |
| **3** | **`tutorial-video-pipeline`** | **`generate_video.py`** | **Figures with narration + audio_asset** |

## Quick Reference

### Per-Figure Video

```bash
# Preview timeline (no video generation)
python scripts/generate_video.py --figure-id 1 --dry-run

# Generate single figure video
python scripts/generate_video.py --figure-id 1

# Generate all figure videos in a section (sequential)
python scripts/generate_video.py --section-id 1

# Force regenerate + custom camera angle
python scripts/generate_video.py --figure-id 1 --force --polar-angle 0.15
```

### Section Video (concatenates figure videos)

```bash
# Concatenate existing figure videos into section video
python scripts/generate_video.py --section-video 1

# Force regenerate
python scripts/generate_video.py --section-video 1 --force
```

### Full Workflow for a Section

```bash
# 1. Ensure server is running
python -m katrain --ui web --port 8001 &

# 2. Generate all figure videos (with concurrency)
python scripts/generate_video.py --section-id 1 --concurrency 3

# 3. Concatenate into section video
python scripts/generate_video.py --section-video 1 --force
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

## Architecture

```
generate_video.py
│
├─ Per-figure pipeline:
│   1. Load figure from DB (board_payload, narration, audio_asset)
│   2. Generate audio with word-level timestamps (edge-tts SubMaker)
│   3. Parse move references from narration (regex: 黑1, 白2位, 第N手)
│   4. Build timeline JSON (moves, subtitles split at Chinese punctuation)
│   5. Capture frames via Playwright (deterministic __setFrame API)
│   6. Mix audio: narration + stone sounds (ffmpeg adelay + amix)
│   7. Compose: raw frames video + mixed audio → MP4
│
├─ Section video pipeline:
│   1. Section title card (Pillow → ffmpeg)
│   2. For each figure: title card "图N (i/total)" + figure video
│   3. Normalize all segments (uniform resolution/fps/encoding)
│   4. ffmpeg concat → section_{id}.mp4
│
└─ Output: data/tutorial_assets/{slug}/video/fig_{id}.mp4
           data/tutorial_assets/{slug}/video/section_{id}.mp4
```

## Frame Capture Details

The recording page (`/record`) renders Board3D with a deterministic `__setFrame(time_ms)` API. Playwright calls this for each frame at 5fps, takes a screenshot, then ffmpeg stitches frames into video. This avoids Playwright's `recordVideo` which cannot reliably capture WebGL canvas in headless mode.

**Camera control:** `StaticCamera` component sets camera position/lookAt directly (no OrbitControls). The `--polar-angle` parameter controls tilt: smaller = more bird's-eye (upright board), larger = flatter side view.

## Output Files

- Per-figure: `data/tutorial_assets/{book_slug}/video/fig_{figure_id}.mp4`
- Per-section: `data/tutorial_assets/{book_slug}/video/section_{section_id}.mp4`
- Resolution: 2560x1440 (2K), H.264, 5fps, AAC audio
- Served via existing `/api/v1/tutorials/assets/` endpoint

## Frontend Integration

- **TutorialFigurePage**: video player below narration (column 3), auto-hides if no video
- **TutorialBookDetailPage**: play icon left of section title, opens fullscreen dialog

## Common Issues

| Issue | Fix |
|-------|-----|
| Board not rendering | Increase warmup time in VideoRecorderPage (default 5s) |
| Camera angle wrong | Use `StaticCamera` (not OrbitControls) for recording mode |
| Stones not appearing | Ensure 300ms+ wait after `__setFrame()` for React re-render |
| ffmpeg drawtext missing | Use Pillow for title cards (drawtext needs ffmpeg built with libfreetype) |
| Audio out of sync | Regenerate audio with timing (edge-tts SubMaker); don't reuse old audio |

## Relationship with Other Skills

- **tutorial-voice-pipeline**: Must run first to generate narration + audio
- **tutorial-recognition-pipeline**: Must run first to generate board_payload
- **tutorial-data-sync**: Sync generated videos to remote server after generation
