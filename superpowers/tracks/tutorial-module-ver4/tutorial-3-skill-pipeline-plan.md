# Tutorial Pipeline: 3-Skill Architecture

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Establish a 3-skill pipeline for Go textbook digitization, with clear execution order enforcement and cross-skill references. Each skill maps to one column in the tutorial figure page UI.

**Date:** 2026-03-30

## Context

The tutorial module converts Go textbook pages into interactive digital tutorials with a 3-column layout:

| Column | Title | Content | Data Source |
|--------|-------|---------|-------------|
| 1 | 原书内容 | Page image + OCR text | `import_book.py` |
| 2 | 棋盘识别 | SGF board + debug panel | `recognize_boards_v2.py` |
| 3 | 语音讲解 | Narration text + audio | `generate_voice.py` |

Currently only 2 skills exist (recognition + voice). The book import step has no skill, and the existing skills don't enforce execution order. This plan adds the missing skill and wires all 3 together.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    Tutorial Pipeline                             │
│                                                                  │
│  ┌──────────────────────┐                                        │
│  │ tutorial-book-import  │  Step 0 (prerequisite)                │
│  │ import_book.py        │  → book_text, page_image_path, bbox   │
│  └──────────┬───────────┘                                        │
│             │                                                    │
│     ┌───────┴────────┐                                           │
│     ▼                ▼                                           │
│  ┌──────────────┐ ┌──────────────────────┐                       │
│  │ tutorial-     │ │ tutorial-voice-       │  Steps 1 & 2        │
│  │ recognition-  │ │ pipeline              │  (independent,      │
│  │ pipeline      │ │ generate_voice.py     │   any order)        │
│  │ recognize_    │ │ → narration,          │                     │
│  │ boards_v2.py  │ │   audio_asset         │                     │
│  │ → board_      │ └──────────────────────┘                      │
│  │   payload     │                                               │
│  └──────────────┘                                                │
└─────────────────────────────────────────────────────────────────┘
```

## Tasks

### Task 1: Create `tutorial-book-import` skill

**File:** `.claude/skills/tutorial-book-import/SKILL.md`

Create a new skill documenting `scripts/import_book.py`. Content must cover:

1. **Frontmatter** with trigger keywords: book import, 导入书籍, import_book, 添加新书, new book
2. **Architecture**: `book.json` + `pages/*.png` → DB records (Book → Chapter → Section → Figure) + asset copy
3. **Running the script**: CLI with `--book-dir`, `--category`, `--force`, `--db-url`
4. **Input format**: Two book.json types (Type A without sections, Type B with sections)
5. **Valid categories**: 入门, 布局, 中盘, 官子
6. **What gets created**: TutorialBook, TutorialChapter, TutorialSection, TutorialFigure records
7. **Asset copying**: pages/*.png → `data/tutorial_assets/{slug}/pages/`
8. **Duplicate handling**: without `--force` skips; with `--force` deletes + recreates
9. **Prerequisites**: book.json must exist in `{book-dir}/output/`, page images must exist
10. **Pipeline Execution Order section** (see Task 4 for template)

**Key details from `import_book.py`:**
- Slug derived from directory name via `slugify()`
- `page_image_path` stored as relative: `tutorial_assets/{slug}/pages/page_{num:03d}.png`
- `page_context_text` = concatenated description elements from same page
- Figure order is 1-based within each section, spanning across pages
- Transaction rollback on any failure
- Logs summary: title, chapters, sections, figures, page images

**Example usage:**
```bash
python scripts/import_book.py \
  --book-dir /Users/fan/Repositories/go-topic-collections/books/布局/曹薰铉布局技巧_中册_曹薰铉_1997 \
  --category 布局
```

### Task 2: Update `tutorial-recognition-pipeline` skill with cross-references

**File:** `.claude/skills/tutorial-recognition-pipeline/SKILL.md`

Add a "Pipeline Execution Order" section (see Task 4 template) after the existing "Architecture" section. This tells Claude to:
- Check that book import has been run (figures exist in DB with `page_image_path`)
- Warn user if section has no figures or no page images
- Reference the other two skills by name

### Task 3: Update `tutorial-voice-pipeline` skill with cross-references

**File:** `.claude/skills/tutorial-voice-pipeline/SKILL.md`

Replace the existing "Relationship with Other Skills" section with the standardized "Pipeline Execution Order" section (Task 4 template). This tells Claude to:
- Check that book import has been run (figures exist in DB with `book_text`)
- Warn user if figures have no `book_text`
- Reference the other two skills by name

### Task 4: Standardized cross-reference section

All 3 skills must include this section (adapted per skill). Template:

```markdown
## Pipeline Execution Order

This skill is part of a 3-skill tutorial digitization pipeline. **Check prerequisites before running.**

| Order | Skill | Script | Prerequisite Check |
|-------|-------|--------|--------------------|
| 0 (first) | `tutorial-book-import` | `import_book.py` | book.json + pages exist in book-dir |
| 1 (after 0) | `tutorial-recognition-pipeline` | `recognize_boards_v2.py` | Figures exist in DB with `page_image_path` and `bbox` |
| 2 (after 0) | `tutorial-voice-pipeline` | `generate_voice.py` | Figures exist in DB with `book_text` |

Steps 1 and 2 are independent — can run in any order or in parallel. Both require step 0.

**Before running this skill, verify:**
- [skill-specific prerequisite check]
- If prerequisites are not met, inform the user which prior skill needs to run first.
```

Each skill adapts the "Before running" bullets:

- **book-import**: No prior skill needed. Just verify `{book-dir}/output/book.json` and `pages/` exist.
- **recognition-pipeline**: Verify section has figures with `page_image_path`. If not → tell user to run `tutorial-book-import` first.
- **voice-pipeline**: Verify section has figures with `book_text`. If not → tell user to run `tutorial-book-import` first.

## Verification

After implementation:

1. **Read all 3 SKILL.md files** and verify each contains the Pipeline Execution Order section
2. **Cross-check**: each skill's table references the other two skills correctly
3. **Trigger test**: mentally simulate invoking each skill — does the prerequisite check make sense?
4. **New book test**: run the following to verify import works:
   ```bash
   python scripts/import_book.py \
     --book-dir /Users/fan/Repositories/go-topic-collections/books/布局/曹薰铉布局技巧_中册_曹薰铉_1997 \
     --category 布局 --force
   ```
   Then check the web UI shows the new book under 布局 category.

## Files to Create/Modify

| Action | File |
|--------|------|
| **Create** | `.claude/skills/tutorial-book-import/SKILL.md` |
| **Edit** | `.claude/skills/tutorial-recognition-pipeline/SKILL.md` |
| **Edit** | `.claude/skills/tutorial-voice-pipeline/SKILL.md` |
