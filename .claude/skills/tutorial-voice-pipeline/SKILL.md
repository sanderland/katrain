---
name: tutorial-voice-pipeline
description: >
  Tutorial voice narration pipeline for Go textbook digitization. Use when generating
  narration text and TTS audio for tutorial figures: running generate_voice.py,
  managing narration rewriting via Claude API, configuring TTS backends (edge-tts /
  CosyVoice), debugging audio output, or editing narration in the web UI.
  Triggers on: voice generation, narration, TTS, audio, 语音讲解, 旁白, edge-tts,
  CosyVoice, generate_voice.
---

# Tutorial Voice Pipeline

Convert Go textbook prose into tutorial narration text and synthesized speech audio.
The pipeline rewrites `book_text` via claude CLI (Max subscription, no API cost) or
Anthropic API into natural tutorial narration, then generates MP3 audio via edge-tts
(or CosyVoice), saving both to the database. Supports parallel processing.

## Architecture

```
Book Import (import_book.py)
  └─ book_text (OCR from textbook)
       │
       ├─ [Step 1] claude CLI rewrite → narration (default, uses Max subscription)
       │     CLI: claude -p --model sonnet
       │     Fallback: Anthropic API (--rewriter api)
       │     Prompt: rephrase for tutorial tone, keep all Go concepts
       │
       ├─ [Step 2] TTS synthesis → MP3 audio file
       │     Backend: edge-tts (default) or CosyVoice (optional)
       │     Voice: zh-CN-XiaoxiaoNeural (default)
       │
       └─ [Step 3] Save to DB → narration + audio_asset columns
             API: PUT /figures/{id}/narration
```

## Pipeline Execution Order

This skill is part of a 3-skill tutorial digitization pipeline. **Check prerequisites before running.**

| Order | Skill | Script | Prerequisite Check |
|-------|-------|--------|--------------------|
| 0 (first) | `tutorial-book-import` | `import_book.py` | book.json + pages exist in book-dir |
| 1 (after 0) | `tutorial-recognition-pipeline` | `recognize_boards_v2.py` | Figures exist in DB with `page_image_path` and `bbox` |
| 2 (after 0) | **`tutorial-voice-pipeline`** | `generate_voice.py` | Figures exist in DB with `book_text` |

Steps 1 and 2 are independent — can run in any order or in parallel. Both require step 0.

**Before running this skill, verify:**
- Section has figures in the database with `book_text` populated.
- If prerequisites are not met, inform the user to run `tutorial-book-import` (`scripts/import_book.py`) first.

## Key Files

| Component | Path |
|-----------|------|
| Pipeline script | `scripts/generate_voice.py` |
| Narration rewriter (lib) | `scripts/lib/narration_rewriter.py` |
| Audio generator (lib) | `scripts/lib/audio_gen.py` |
| DB models | `katrain/web/core/models_db.py` (TutorialFigure) |
| DB queries | `katrain/web/tutorials/db_queries.py` (`update_figure_narration`) |
| API schemas | `katrain/web/tutorials/models.py` (`NarrationUpdate`) |
| API endpoints | `katrain/web/api/v1/endpoints/tutorials.py` |
| Audio player UI | `katrain/web/ui/src/galaxy/components/tutorials/AudioPlayer.tsx` |
| Figure page UI | `katrain/web/ui/src/galaxy/pages/tutorials/TutorialFigurePage.tsx` |
| Audio output dir | `data/tutorial_assets/{book_slug}/audio/` |

## Running the Pipeline

```bash
# Generate narration + audio (default: claude CLI + edge-tts, 5 parallel tasks)
python scripts/generate_voice.py --section-id <ID>

# Higher parallelism
python scripts/generate_voice.py --section-id <ID> --concurrency 8

# Dry run (preview what would be generated, no DB writes or API calls)
python scripts/generate_voice.py --section-id <ID> --dry-run

# Force re-generate (overwrite existing narration + audio)
python scripts/generate_voice.py --section-id <ID> --force

# Use Anthropic API instead of claude CLI (costs money)
python scripts/generate_voice.py --section-id <ID> --rewriter api

# Use CosyVoice backend instead of edge-tts
python scripts/generate_voice.py --section-id <ID> --tts cosyvoice --cosyvoice-url http://localhost:50000

# Use a different edge-tts voice
python scripts/generate_voice.py --section-id <ID> --voice zh-CN-YunxiNeural
```

### CLI Options

| Flag | Default | Description |
|------|---------|-------------|
| `--section-id` | (required) | Section ID to process |
| `--force` | `false` | Re-generate even if narration/audio already exists |
| `--dry-run` | `false` | Preview without writing to DB or generating audio |
| `--rewriter` | `cli` | Narration rewriter: `cli` (claude CLI, Max subscription, free) or `api` (Anthropic API, billed) |
| `--model` | `sonnet` | Model for claude CLI rewriter |
| `--concurrency` | `5` | Max parallel narration+TTS tasks |
| `--tts` | `edge-tts` | TTS backend: `edge-tts` or `cosyvoice` |
| `--cosyvoice-url` | `http://localhost:50000` | CosyVoice HTTP API base URL |
| `--voice` | `zh-CN-XiaoxiaoNeural` | edge-tts voice name |

### Processing Logic

Figures within a section are processed **in parallel** (up to `--concurrency` limit):

1. **Skip** if `book_text` is empty (no source text to narrate)
2. **Skip** if `narration` AND `audio_asset` both exist (unless `--force`)
3. **Step 1**: Rewrite `book_text` → `narration` via claude CLI or API (or reuse existing narration if only audio is missing)
4. **Step 2**: Generate TTS audio → `data/tutorial_assets/{book_slug}/audio/fig_{figure_id}.mp3`
5. **Step 3**: Save all results to database in a single commit

On narration failure, falls back to using `book_text` verbatim. On audio failure, `audio_asset` is set to `None`.

## Narration Rewriting

### Rewriter: claude CLI (default)

- **Command**: `claude -p --model sonnet` (subprocess)
- **Auth**: Uses Max subscription (no API cost)
- **Parallelism**: Multiple `claude` CLI processes via `asyncio.Semaphore`

### Rewriter: Anthropic API (fallback)

- **Model**: `claude-sonnet-4-20250514`
- **Auth**: `ANTHROPIC_API_KEY` environment variable (billed separately)
- **Max tokens**: 1024

### Prompt

```
You are helping create Go (围棋) tutorial narration for learners.

Rewrite the following Chinese Go book text. Requirements:
- Keep ALL concepts, technical terms, and strategic content intact
- Rephrase sentence structure and word choice so it doesn't feel like a direct copy
- Maintain the same level of detail and meaning
- Write in natural, clear Mandarin Chinese suitable for a digital tutorial
- Use a warm, conversational tone as if explaining to a student
- Output ONLY the rewritten Chinese text — no translation, no explanation, no quotes

Original text:
{text}
```

### Library Module

`scripts/lib/narration_rewriter.py` provides a reusable `rewrite_narration()` function with the same prompt (uses Anthropic API with `claude-opus-4-6`). The main script has its own `rewrite_narration_cli()` (claude CLI, default) and `rewrite_narration_api()` (Anthropic API, fallback) and does **not** import from the lib module. The higher-level script `scripts/generate_tutorial_v003.py` imports from the lib module.

## TTS Backends

### edge-tts (Default)

Free Microsoft Edge TTS service via the `edge-tts` Python package. No API key required.

- **Package**: `edge-tts` (in project dependencies)
- **Default voice**: `zh-CN-XiaoxiaoNeural` (female Mandarin Chinese)
- **Output**: MP3 file
- **Latency**: ~1-3 seconds per figure

Other available Chinese voices: `zh-CN-YunxiNeural` (male), `zh-CN-XiaoyiNeural`, `zh-CN-YunjianNeural`.

### CosyVoice (Optional)

Self-hosted TTS via CosyVoice HTTP API. Requires running a CosyVoice server.

- **API**: `POST {base_url}/tts` with JSON body `{"text": "...", "speaker": "中文女"}`
- **Default URL**: `http://localhost:50000`
- **Timeout**: 60 seconds
- **Output**: MP3 file

### Library Fallback

The lib module (`scripts/lib/audio_gen.py`) writes a minimal silent MP3 stub when TTS fails, ensuring a file always exists. The main script (`generate_voice.py`) instead sets `audio_asset` to `None` on failure — no stub file is written.

## Data Model

### TutorialFigure Columns (voice-related)

| Column | Type | Source | Description |
|--------|------|--------|-------------|
| `book_text` | `Text` | `import_book.py` | Original OCR text from book (input) |
| `page_context_text` | `Text` | `import_book.py` | Surrounding page context (not used by voice pipeline) |
| `narration` | `Text` | `generate_voice.py` | Rewritten narration text (output) |
| `audio_asset` | `String(512)` | `generate_voice.py` | Relative path to MP3 file (output) |

### Audio Asset Path Convention

```
# File on disk:
data/tutorial_assets/{book_slug}/audio/fig_{figure_id}.mp3

# Stored in DB (audio_asset column):
tutorial_assets/{book_slug}/audio/fig_{figure_id}.mp3

# Served via API:
GET /api/v1/tutorials/assets/tutorial_assets/{book_slug}/audio/fig_{figure_id}.mp3

# Frontend URL construction:
TutorialAPI.assetUrl(figure.audio_asset)
```

## API Endpoints

### Update Narration

```
PUT /api/v1/tutorials/figures/{figure_id}/narration
```

**Request body** (`NarrationUpdate`):
```json
{
  "narration": "改写后的讲解文本...",
  "audio_asset": "tutorial_assets/some-book/audio/fig_42.mp3"
}
```

`audio_asset` is optional — if omitted, only narration text is updated.

**Response**: Full `TutorialFigureOut` object.

### Serve Audio Asset

```
GET /api/v1/tutorials/assets/{asset_path}
```

Serves static files from `data/` directory. Path traversal is rejected by `_safe_asset_path()`.

## Frontend Display

Column 3 ("语音讲解") in `TutorialFigurePage.tsx`:
- If `narration` exists: shows narration text + `<AudioPlayer>` component with play/pause
- If `narration` is empty: shows italic placeholder "暂无讲解文本。运行 generate_voice.py 生成。"

`AudioPlayer.tsx` is an HTML5 audio player with play/pause toggle, error state indicator, and `onEnded` callback.

## Prerequisites

1. **Book must be imported** — run `scripts/import_book.py` first so `book_text` is populated
2. **`ANTHROPIC_API_KEY`** — must be set for Claude API narration rewriting
3. **`edge-tts` package** — installed via `uv sync` (in project dependencies)
4. **CosyVoice server** (optional) — only needed if using `--tts cosyvoice`

## Finding Section IDs

```python
from katrain.web.core.db import SessionLocal
from katrain.web.core.models_db import TutorialSection, TutorialFigure

db = SessionLocal()
for s in db.query(TutorialSection).all():
    figs = db.query(TutorialFigure).filter_by(section_id=s.id).all()
    has_narration = [f for f in figs if f.narration]
    has_audio = [f for f in figs if f.audio_asset]
    print(f"Section {s.id}: {s.title} — {len(figs)} figs "
          f"({len(has_narration)} narrated, {len(has_audio)} with audio)")
```
