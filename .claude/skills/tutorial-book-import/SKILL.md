---
name: tutorial-book-import
description: >
  Go textbook import pipeline for tutorial digitization. Use when importing a new
  book into the tutorial database: running import_book.py, preparing book.json,
  setting up page assets, or troubleshooting import failures.
  Triggers on: book import, 导入书籍, import_book, 添加新书, new book, 新书导入.
---

# Tutorial Book Import

Import Go textbook data from `book.json` + page screenshots into the tutorial database.
This is step 0 (prerequisite) of the tutorial digitization pipeline — both the recognition
and voice pipelines depend on the records and assets created here.

## Architecture

```
{book-dir}/output/
  ├── book.json              ← structured book metadata + figure references
  └── pages/
      ├── page_001.png       ← page screenshots from PDF
      ├── page_002.png
      └── ...
          │
          ▼
  import_book.py
          │
          ├── DB records: TutorialBook → TutorialChapter → TutorialSection → TutorialFigure
          └── Asset copy: pages/*.png → data/tutorial_assets/{slug}/pages/
```

## Key Files

| Component | Path |
|-----------|------|
| Import script | `scripts/import_book.py` |
| DB models | `katrain/web/core/models_db.py` (TutorialBook, TutorialChapter, TutorialSection, TutorialFigure) |
| Asset output | `data/tutorial_assets/{slug}/pages/` |

## Running the Script

```bash
# Standard import
python scripts/import_book.py \
  --book-dir /path/to/books/布局/曹薰铉布局技巧_中册_曹薰铉_1997 \
  --category 布局

# Force re-import (deletes existing + recreates)
python scripts/import_book.py \
  --book-dir /path/to/books/布局/曹薰铉布局技巧_中册_曹薰铉_1997 \
  --category 布局 --force

# Custom database URL
python scripts/import_book.py \
  --book-dir /path/to/book \
  --category 入门 --db-url sqlite:///my.db
```

### CLI Options

| Flag | Default | Description |
|------|---------|-------------|
| `--book-dir` | (required) | Path to book directory containing `output/book.json` |
| `--category` | (required) | Top-level category: `入门`, `布局`, `中盘`, `官子` |
| `--force` | `false` | Delete + recreate if book already imported |
| `--db-url` | app settings | Override database URL |

## Input Format: book.json

Located at `{book-dir}/output/book.json`. Two formats supported:

### Type A: Without sections (chapters contain pages directly)

```json
{
  "title": "Book Title",
  "author": "Author Name",
  "translator": "Translator (optional)",
  "chapters": [
    {
      "chapter": "第1章",
      "title": "Chapter Title",
      "intro": [
        {
          "page": 12,
          "elements": [
            {"type": "description", "text": "Explanatory text..."},
            {"type": "figure_ref", "label": "图1", "text": "Figure caption", "bbox": [x, y, w, h]}
          ]
        }
      ]
    }
  ]
}
```

Type A creates a synthetic section per chapter (section_number = chapter number, title = chapter title).

### Type B: With sections (chapters → sections → pages)

```json
{
  "title": "Book Title",
  "author": "Author Name",
  "chapters": [
    {
      "chapter": "第1章",
      "title": "Chapter Title",
      "sections": [
        {
          "section": "1",
          "title": "Section Title",
          "pages": [
            {
              "page": 15,
              "elements": [
                {"type": "description", "text": "..."},
                {"type": "figure_ref", "label": "图1", "text": "...", "bbox": [x, y, w, h]}
              ]
            }
          ]
        }
      ]
    }
  ]
}
```

## What Gets Created

| Record | Key Fields |
|--------|------------|
| `TutorialBook` | `category`, `subcategory="棋书"`, `title`, `author`, `translator`, `slug`, `asset_dir` |
| `TutorialChapter` | `book_id`, `chapter_number`, `title`, `order` (1-based) |
| `TutorialSection` | `chapter_id`, `section_number`, `title`, `order` (1-based) |
| `TutorialFigure` | `section_id`, `page`, `figure_label`, `book_text`, `page_context_text`, `bbox`, `page_image_path`, `order` (1-based within section) |

### Key Details

- **Slug**: derived from directory name via `slugify()` (lowercase, special chars removed, spaces → hyphens)
- **`page_image_path`**: stored as relative path `tutorial_assets/{slug}/pages/page_{num:03d}.png`
- **`page_context_text`**: concatenated `description` elements from the same page
- **`book_text`**: from `figure_ref` element's `text` field — this is what the voice pipeline narrates
- **`bbox`**: bounding box from `figure_ref` element — used by recognition pipeline to crop diagrams
- **Figure order**: 1-based within each section, spanning across pages
- **Transaction**: full rollback on any failure

## Asset Copying

Page images are copied from `{book-dir}/output/pages/` → `data/tutorial_assets/{slug}/pages/`.
- Only `page_*.png` files are copied
- Existing files are not overwritten (idempotent)
- Script fails if no page images found

## Duplicate Handling

- Without `--force`: logs warning and returns existing book, no changes made
- With `--force`: deletes existing book (cascades to chapters → sections → figures) then reimports

## Valid Categories

`入门`, `布局`, `中盘`, `官子`

## Pipeline Execution Order

This skill is part of a 3-skill tutorial digitization pipeline. **Check prerequisites before running.**

| Order | Skill | Script | Prerequisite Check |
|-------|-------|--------|--------------------|
| 0 (first) | **`tutorial-book-import`** | `import_book.py` | book.json + pages exist in book-dir |
| 1 (after 0) | `tutorial-recognition-pipeline` | `recognize_boards_v2.py` | Figures exist in DB with `page_image_path` and `bbox` |
| 2 (after 0) | `tutorial-voice-pipeline` | `generate_voice.py` | Figures exist in DB with `book_text` |

Steps 1 and 2 are independent — can run in any order or in parallel. Both require step 0.

**Before running this skill, verify:**
- `{book-dir}/output/book.json` exists and is valid JSON
- `{book-dir}/output/pages/` contains `page_*.png` files
- No prior skill needed — this is the first step in the pipeline.

## Output Summary

On success, the script logs:
```
Imported: {title} → {N} chapters, {N} sections, {N} figures, {N} page images
```
