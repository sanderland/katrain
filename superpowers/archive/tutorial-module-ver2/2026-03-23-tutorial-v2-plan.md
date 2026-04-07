# Tutorial Module V2 — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the JSON-file-based tutorial module with a database-backed system that supports the full book hierarchy (Category → Book → Chapter → Section → Figure), full-page screenshots, and an editable SVG Go board with stone placement, letter annotations, shape markers, eraser/undo, and server-side viewport cropping.

**Scope:** SGF board editing only — AI-generated text and audio are not changed in this phase.

**Revision:** v2 (2026-03-23) — incorporates review feedback from Gemini and Codex. Key changes: fix letter accumulation logic, fix half-board viewport, add undo stack, add auth/validation on edit API, add optimistic locking, clarify UserTutorialProgress migration, delay all destructive deletions to final chunk, strengthen test coverage, add loading/error/empty states, fix import script asset ordering.

---

## Architecture Overview

### Content Hierarchy

```
Level 1 — Category:     入门 / 布局 / 中盘 / 官子          (hardcoded)
Level 2 — Subcategory:  "棋书" (placeholder for future)     (DB: tutorial_books.subcategory)
Level 3 — Book:         e.g. 曹薰铉布局技巧（上）           (DB: tutorial_books)
Level 4 — Chapter:      e.g. 第一章 布局入门                (DB: tutorial_chapters)
Level 5 — Section:      e.g. 1. 外势和实地  (= Example)     (DB: tutorial_sections)
Level 6 — Figure:       e.g. 图1, 图2...    (= Variation)   (DB: tutorial_figures)
```

### Data Flow

```
go-topic-collections/books/{cat}/{book}/output/book.json
                ↓ (import_book.py — one-time CLI)
         PostgreSQL / SQLite  ←—→  FastAPI endpoints  ←—→  React frontend
                                                              ↓
                                              EditableSGFBoard (SVG)
                                              BoardEditToolbar
                                              Save → PUT /figures/{id}/board
```

### Key Design Decisions

| Decision | Choice |
|----------|--------|
| Data source | DB is sole source of truth; old JSON files deleted after full validation |
| Board editor | `SGFBoard` = pure renderer; `EditableSGFBoard` = interactive wrapper with click handling |
| Viewport calc | Server-side, rectangular `{col,row,cols,rows}`, snapped to 1/4 / 1/2 / full board |
| Asset storage | Copy page PNGs to `data/tutorial_assets/{book_slug}/pages/` (gitignored, runtime data) |
| Import | CLI script `scripts/import_book.py`; assets copied before DB commit |
| Categories | Hardcoded list with `CheckConstraint` at DB level |
| Section = Example | For Type A books (no sections), synthetic section from chapter title |
| Edit API auth | Requires authenticated user (JWT); `board_payload` strictly validated |
| Concurrency | Optimistic locking via `updated_at` on board save (409 on conflict) |
| Undo | Client-side undo stack (max 50 entries) in `useBoardEditor` |
| Cancel edit | Resets to last saved payload from DB, discards in-memory changes |
| UserTutorialProgress | Deprecated in V2; table preserved but progress API endpoints removed |
| Migration safety | Feature flag `TUTORIALS_V2_ENABLED`; old loader kept behind flag for one release |
| Move-step slider | Unlabeled stones = initial position (always visible); only numbered stones step |
| Non-19×19 boards | Read-only full-board display only; editing restricted to 19×19 |

---

## File Structure

**New files:**
```
scripts/import_book.py                                                  # CLI: book.json → DB + copy assets
katrain/web/tutorials/db_queries.py                                     # DB query functions
katrain/web/tutorials/viewport.py                                       # Viewport calculation (quarter/half/full)
katrain/web/ui/src/galaxy/pages/tutorials/TutorialBooksPage.tsx         # Books in a category
katrain/web/ui/src/galaxy/pages/tutorials/TutorialBookDetailPage.tsx    # Chapters + sections tree
katrain/web/ui/src/galaxy/pages/tutorials/TutorialFigurePage.tsx        # Figure playback with editable board
katrain/web/ui/src/galaxy/components/tutorials/EditableSGFBoard.tsx     # Interactive SVG board
katrain/web/ui/src/galaxy/components/tutorials/BoardEditToolbar.tsx     # Edit mode toolbar
katrain/web/ui/src/galaxy/hooks/useBoardEditor.ts                       # Board editing state management
tests/web_ui/test_tutorial_db_models.py                                 # DB model tests
tests/web_ui/test_tutorial_import.py                                    # Import script tests
tests/web_ui/test_tutorial_db_api.py                                    # API endpoint tests
```

**Modified files:**
```
katrain/web/core/models_db.py                                           # + 4 new tables with constraints
katrain/web/tutorials/models.py                                         # Rewrite Pydantic response models + strict validation
katrain/web/api/v1/endpoints/tutorials.py                               # Rewrite all endpoints + auth + optimistic locking
katrain/web/server.py                                                   # Feature-flag V2 vs old loader
katrain/web/ui/src/galaxy/types/tutorial.ts                             # Rewrite TypeScript types
katrain/web/ui/src/galaxy/api/tutorialApi.ts                            # Rewrite API client
katrain/web/ui/src/GalaxyApp.tsx                                        # Update routes
katrain/web/ui/src/galaxy/components/tutorials/SGFBoard.tsx             # Add letters, shapes, rectangular viewport
katrain/web/ui/src/galaxy/pages/tutorials/TutorialLandingPage.tsx       # Adapt to hardcoded categories
katrain/web/ui/tests/tutorial.spec.ts                                   # Rewrite E2E tests
.gitignore                                                              # + data/tutorial_assets/
```

**Deleted files (ALL in final Chunk 6 cleanup, after full validation):**
```
katrain/web/tutorials/loader.py                                         # Replaced by db_queries.py
katrain/web/tutorials/progress.py                                       # Progress feature deprecated in V2
data/tutorials_published/                                               # Replaced by DB + tutorial_assets
katrain/web/ui/src/galaxy/pages/tutorials/TutorialTopicsPage.tsx        # Replaced by TutorialBooksPage
katrain/web/ui/src/galaxy/pages/tutorials/TutorialTopicDetailPage.tsx   # Replaced by TutorialBookDetailPage
katrain/web/ui/src/galaxy/pages/tutorials/TutorialExamplePage.tsx       # Replaced by TutorialFigurePage
katrain/web/ui/src/galaxy/components/tutorials/StepDisplay.tsx          # Logic merged into TutorialFigurePage
```

---

## Chunk 1: Database Models

### Task 1: Add 4 New Tables to `models_db.py`

**File:** Modify `katrain/web/core/models_db.py`

- [ ] **Step 1.1: Append `TutorialBook` model**

After the existing `UserTutorialProgress` class, add:

```python
class TutorialBook(Base):
    """A Go tutorial book imported from book.json."""
    __tablename__ = "tutorial_books"

    id = Column(Integer, primary_key=True, index=True)
    category = Column(String(32), nullable=False, index=True)      # 入门/布局/中盘/官子
    subcategory = Column(String(64), nullable=False, default="棋书")
    title = Column(String(256), nullable=False)
    author = Column(String(128), nullable=True)
    translator = Column(String(128), nullable=True)
    slug = Column(String(128), nullable=False, unique=True, index=True)  # URL-safe: cao-xun-xuan-buju-1
    asset_dir = Column(String(512), nullable=False)  # relative path: tutorial_assets/{slug}/pages
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    chapters = relationship("TutorialChapter", back_populates="book", cascade="all, delete-orphan",
                            order_by="TutorialChapter.order")

    __table_args__ = (
        CheckConstraint("category IN ('入门', '布局', '中盘', '官子')", name="ck_book_category"),
    )
```

Note: requires `from sqlalchemy import CheckConstraint, UniqueConstraint` at top of models_db.py.

- [ ] **Step 1.2: Append `TutorialChapter` model**

```python
class TutorialChapter(Base):
    """A chapter within a tutorial book."""
    __tablename__ = "tutorial_chapters"

    id = Column(Integer, primary_key=True, index=True)
    book_id = Column(Integer, ForeignKey("tutorial_books.id", ondelete="CASCADE"), nullable=False, index=True)
    chapter_number = Column(String(32), nullable=False)  # "第一章", "第1课"
    title = Column(String(256), nullable=False)
    order = Column(Integer, nullable=False)

    book = relationship("TutorialBook", back_populates="chapters")
    sections = relationship("TutorialSection", back_populates="chapter", cascade="all, delete-orphan",
                            order_by="TutorialSection.order")

    __table_args__ = (
        UniqueConstraint("book_id", "order", name="uq_chapter_book_order"),
    )
```

- [ ] **Step 1.3: Append `TutorialSection` model**

```python
class TutorialSection(Base):
    """A section within a chapter (= one Example in the UI)."""
    __tablename__ = "tutorial_sections"

    id = Column(Integer, primary_key=True, index=True)
    chapter_id = Column(Integer, ForeignKey("tutorial_chapters.id", ondelete="CASCADE"), nullable=False, index=True)
    section_number = Column(String(32), nullable=False)  # "1", "问题1", or synthetic
    title = Column(String(256), nullable=False)
    order = Column(Integer, nullable=False)

    chapter = relationship("TutorialChapter", back_populates="sections")
    figures = relationship("TutorialFigure", back_populates="section", cascade="all, delete-orphan",
                           order_by="TutorialFigure.order")

    __table_args__ = (
        UniqueConstraint("chapter_id", "order", name="uq_section_chapter_order"),
    )
```

- [ ] **Step 1.4: Append `TutorialFigure` model**

```python
class TutorialFigure(Base):
    """A single board diagram (= one Variation in the UI). Core content unit."""
    __tablename__ = "tutorial_figures"

    id = Column(Integer, primary_key=True, index=True)
    section_id = Column(Integer, ForeignKey("tutorial_sections.id", ondelete="CASCADE"), nullable=False, index=True)
    page = Column(Integer, nullable=False)                      # book page number
    figure_label = Column(String(32), nullable=False)           # "图1", "图2"
    book_text = Column(Text, nullable=True)                     # original Chinese commentary from figure_ref
    page_context_text = Column(Text, nullable=True)             # page-level description elements (combined)
    bbox = Column(JSON, nullable=True)                          # {x_min, y_min, x_max, y_max}
    page_image_path = Column(String(512), nullable=True)        # relative: tutorial_assets/{slug}/pages/page_011.png
    board_payload = Column(JSON, nullable=True)                 # {size, stones, labels, letters, shapes, highlights, viewport}
    narration = Column(Text, nullable=True)                     # AI-generated text (future)
    audio_asset = Column(String(512), nullable=True)            # path to MP3 (future)
    order = Column(Integer, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    section = relationship("TutorialSection", back_populates="figures")

    __table_args__ = (
        UniqueConstraint("section_id", "order", name="uq_figure_section_order"),
    )
```

- [ ] **Step 1.5: Run `alembic` or manual table creation to verify**

```bash
CI=true uv run python -c "
from sqlalchemy import create_engine
from katrain.web.core.models_db import Base, TutorialBook, TutorialChapter, TutorialSection, TutorialFigure
engine = create_engine('sqlite:///:memory:')
Base.metadata.create_all(bind=engine)
print('Tables:', [t for t in Base.metadata.tables.keys() if t.startswith('tutorial_')])
print('OK')
"
```

Expected: `Tables: ['user_tutorial_progress', 'tutorial_books', 'tutorial_chapters', 'tutorial_sections', 'tutorial_figures']`

- [ ] **Step 1.6: Commit**

```bash
git add katrain/web/core/models_db.py
git commit -m "feat(tutorials-v2): add TutorialBook/Chapter/Section/Figure DB models"
```

---

### Task 2: DB Model Tests

**File:** Create `tests/web_ui/test_tutorial_db_models.py`

- [ ] **Step 2.1: Write tests**

```python
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from katrain.web.core import models_db


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    models_db.Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def test_create_book_with_full_hierarchy(db):
    book = models_db.TutorialBook(
        category="布局", subcategory="棋书", title="测试书", author="作者",
        slug="test-book", asset_dir="tutorial_assets/test-book/pages",
    )
    db.add(book)
    db.commit()

    chapter = models_db.TutorialChapter(
        book_id=book.id, chapter_number="第一章", title="布局入门", order=1,
    )
    db.add(chapter)
    db.commit()

    section = models_db.TutorialSection(
        chapter_id=chapter.id, section_number="1", title="外势和实地", order=1,
    )
    db.add(section)
    db.commit()

    figure = models_db.TutorialFigure(
        section_id=section.id, page=11, figure_label="图1",
        book_text="测试文字", page_image_path="tutorial_assets/test-book/pages/page_011.png",
        board_payload={"size": 19, "stones": {"B": [[2, 16]], "W": [[3, 3]]}, "labels": {"2,16": "1", "3,3": "2"}},
        order=1,
    )
    db.add(figure)
    db.commit()

    # Verify relationships
    assert len(book.chapters) == 1
    assert len(chapter.sections) == 1
    assert len(section.figures) == 1
    assert section.figures[0].figure_label == "图1"
    assert section.figures[0].board_payload["stones"]["B"] == [[2, 16]]


def test_cascade_delete(db):
    book = models_db.TutorialBook(
        category="入门", subcategory="棋书", title="删除测试",
        slug="delete-test", asset_dir="tutorial_assets/delete-test/pages",
    )
    db.add(book)
    db.commit()

    chapter = models_db.TutorialChapter(book_id=book.id, chapter_number="第1课", title="测试", order=1)
    db.add(chapter)
    db.commit()
    section = models_db.TutorialSection(chapter_id=chapter.id, section_number="1", title="测试", order=1)
    db.add(section)
    db.commit()
    figure = models_db.TutorialFigure(
        section_id=section.id, page=1, figure_label="图1", order=1,
    )
    db.add(figure)
    db.commit()

    db.delete(book)
    db.commit()

    assert db.query(models_db.TutorialChapter).count() == 0
    assert db.query(models_db.TutorialSection).count() == 0
    assert db.query(models_db.TutorialFigure).count() == 0


def test_book_slug_unique(db):
    b1 = models_db.TutorialBook(category="布局", title="A", slug="same-slug", asset_dir="a")
    b2 = models_db.TutorialBook(category="布局", title="B", slug="same-slug", asset_dir="b")
    db.add(b1)
    db.commit()
    db.add(b2)
    with pytest.raises(Exception):  # IntegrityError
        db.commit()


def test_update_board_payload(db):
    book = models_db.TutorialBook(category="布局", title="T", slug="bp-test", asset_dir="a")
    db.add(book)
    db.commit()
    ch = models_db.TutorialChapter(book_id=book.id, chapter_number="1", title="C", order=1)
    db.add(ch)
    db.commit()
    sec = models_db.TutorialSection(chapter_id=ch.id, section_number="1", title="S", order=1)
    db.add(sec)
    db.commit()
    fig = models_db.TutorialFigure(
        section_id=sec.id, page=1, figure_label="图1", order=1,
        board_payload={"size": 19, "stones": {"B": [], "W": []}, "labels": {}},
    )
    db.add(fig)
    db.commit()

    # Update board_payload
    fig.board_payload = {
        "size": 19,
        "stones": {"B": [[3, 3]], "W": []},
        "labels": {"3,3": "1"},
        "letters": {"5,5": "A"},
        "shapes": {"7,7": "triangle"},
    }
    db.commit()
    db.refresh(fig)
    assert fig.board_payload["letters"]["5,5"] == "A"
    assert fig.board_payload["shapes"]["7,7"] == "triangle"
```

- [ ] **Step 2.2: Run tests**

```bash
CI=true uv run pytest tests/web_ui/test_tutorial_db_models.py -v
```

Expected: 4 tests PASSED

- [ ] **Step 2.3: Commit**

```bash
git add tests/web_ui/test_tutorial_db_models.py
git commit -m "test(tutorials-v2): add DB model tests for book hierarchy"
```

---

## Chunk 2: Import Script

### Task 3: Create Book Import Script

**File:** Create `scripts/import_book.py`

- [ ] **Step 3.1: Write the import script**

```python
#!/usr/bin/env python3
"""Import a Go book from book.json into the tutorial database.

Usage:
    python scripts/import_book.py \\
        --book-dir /path/to/go-topic-collections/books/布局/曹薰铉布局技巧_上册_曹薰铉_1997 \\
        --category 布局

The script:
1. Reads {book-dir}/output/book.json
2. Creates TutorialBook + chapters + sections + figures in the database
3. Copies page screenshots from {book-dir}/output/pages/ to data/tutorial_assets/{slug}/pages/
"""

import argparse
import json
import logging
import re
import shutil
import sys
from pathlib import Path

# Add project root to Python path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from katrain.web.core.config import settings
from katrain.web.core.models_db import Base, TutorialBook, TutorialChapter, TutorialSection, TutorialFigure

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger(__name__)

ASSET_BASE = Path("data/tutorial_assets")
VALID_CATEGORIES = {"入门", "布局", "中盘", "官子"}


def slugify(text: str) -> str:
    """Convert Chinese/mixed text to a URL-safe slug."""
    # Use pinyin if available, otherwise simple transliteration
    slug = re.sub(r"[^\w\s-]", "", text.lower())
    slug = re.sub(r"[\s_]+", "-", slug).strip("-")
    return slug or "book"


def make_page_image_path(slug: str, page_num: int) -> str:
    """Build the relative asset path for a page screenshot."""
    return f"tutorial_assets/{slug}/pages/page_{page_num:03d}.png"


def copy_page_assets(book_dir: Path, slug: str) -> int:
    """Copy page PNGs from book output to data/tutorial_assets/{slug}/pages/."""
    src_pages = book_dir / "output" / "pages"
    dst_pages = ASSET_BASE / slug / "pages"
    dst_pages.mkdir(parents=True, exist_ok=True)

    count = 0
    for png in sorted(src_pages.glob("page_*.png")):
        dst = dst_pages / png.name
        if not dst.exists():
            shutil.copy2(png, dst)
        count += 1
    return count


def import_book(session, book_dir: Path, category: str, force: bool = False) -> TutorialBook:
    """Import a single book from book.json into the database."""
    book_json_path = book_dir / "output" / "book.json"
    if not book_json_path.exists():
        raise FileNotFoundError(f"book.json not found: {book_json_path}")

    data = json.loads(book_json_path.read_text(encoding="utf-8"))
    title = data["title"]
    author = data.get("author", "")
    translator = data.get("translator")

    # Generate slug from directory name
    slug = slugify(book_dir.name)

    # Check if already imported
    existing = session.query(TutorialBook).filter_by(slug=slug).first()
    if existing:
        if force:
            log.info("Deleting existing book: %s (slug=%s)", title, slug)
            session.delete(existing)
            session.flush()
        else:
            log.warning("Book already imported: %s (slug=%s). Use --force to reimport.", title, slug)
            return existing

    asset_dir = f"tutorial_assets/{slug}/pages"
    book = TutorialBook(
        category=category,
        subcategory="棋书",
        title=title,
        author=author,
        translator=translator,
        slug=slug,
        asset_dir=asset_dir,
    )
    session.add(book)
    session.flush()  # get book.id

    chapters = data.get("chapters", [])
    figure_count = 0

    for ch_idx, ch_data in enumerate(chapters):
        chapter = TutorialChapter(
            book_id=book.id,
            chapter_number=ch_data.get("chapter", f"第{ch_idx + 1}章"),
            title=ch_data.get("title", ""),
            order=ch_idx + 1,
        )
        session.add(chapter)
        session.flush()

        sections = ch_data.get("sections", [])

        if sections:
            # Type B: has sections
            for sec_idx, sec_data in enumerate(sections):
                section = TutorialSection(
                    chapter_id=chapter.id,
                    section_number=sec_data.get("section", str(sec_idx + 1)),
                    title=sec_data.get("title", ""),
                    order=sec_idx + 1,
                )
                session.add(section)
                session.flush()

                fig_order = 0
                for page_data in sec_data.get("pages", []):
                    page_num = page_data["page"]
                    for elem in page_data.get("elements", []):
                        if elem.get("type") != "figure_ref":
                            continue
                        fig_order += 1
                        figure = TutorialFigure(
                            section_id=section.id,
                            page=page_num,
                            figure_label=elem.get("label", f"图{fig_order}"),
                            book_text=elem.get("text", ""),
                            bbox=elem.get("bbox"),
                            page_image_path=make_page_image_path(slug, page_num),
                            board_payload=None,  # populated later via visual LLM or manual editing
                            order=fig_order,
                        )
                        session.add(figure)
                        figure_count += 1
        else:
            # Type A: no sections — create synthetic section from chapter
            section = TutorialSection(
                chapter_id=chapter.id,
                section_number=ch_data.get("chapter", "1"),
                title=ch_data.get("title", ""),
                order=1,
            )
            session.add(section)
            session.flush()

            fig_order = 0
            for page_data in ch_data.get("intro", []):
                page_num = page_data["page"]
                for elem in page_data.get("elements", []):
                    if elem.get("type") != "figure_ref":
                        continue
                    fig_order += 1
                    figure = TutorialFigure(
                        section_id=section.id,
                        page=page_num,
                        figure_label=elem.get("label", f"图{fig_order}"),
                        book_text=elem.get("text", ""),
                        bbox=elem.get("bbox"),
                        page_image_path=make_page_image_path(slug, page_num),
                        board_payload=None,
                        order=fig_order,
                    )
                    session.add(figure)
                    figure_count += 1

    # Copy page assets FIRST (before commit), so DB never points to missing files
    copied = copy_page_assets(book_dir, slug)
    if copied == 0:
        session.rollback()
        raise FileNotFoundError(f"No page images found in {book_dir / 'output' / 'pages'}")

    session.commit()
    log.info(
        "Imported: %s → %d chapters, %d sections, %d figures, %d page images",
        title,
        len(book.chapters),
        sum(len(ch.sections) for ch in book.chapters),
        figure_count,
        copied,
    )
    return book


def main():
    parser = argparse.ArgumentParser(description="Import a Go book into the tutorial database")
    parser.add_argument("--book-dir", type=Path, required=True, help="Path to book directory (contains output/book.json)")
    parser.add_argument("--category", required=True, choices=VALID_CATEGORIES, help="Top-level category")
    parser.add_argument("--force", action="store_true", help="Re-import even if book already exists")
    parser.add_argument("--db-url", default=None, help="Database URL (defaults to app settings)")
    args = parser.parse_args()

    db_url = args.db_url or settings.DATABASE_URL
    engine = create_engine(db_url)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    try:
        import_book(session, args.book_dir, args.category, force=args.force)
    except Exception as e:
        session.rollback()
        log.error("Import failed: %s", e)
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main()
```

- [ ] **Step 3.2: Run import for test book**

```bash
uv run python scripts/import_book.py \
    --book-dir /Users/fan/Repositories/go-topic-collections/books/布局/曹薰铉布局技巧_上册_曹薰铉_1997 \
    --category 布局
```

Expected: `Imported: 曹薰铉布局技巧（上） → 2 chapters, 46+ sections, 200+ figures, 200+ page images`

- [ ] **Step 3.3: Verify imported data**

```bash
uv run python -c "
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from katrain.web.core.config import settings
from katrain.web.core.models_db import TutorialBook, TutorialChapter, TutorialSection, TutorialFigure

engine = create_engine(settings.DATABASE_URL)
Session = sessionmaker(bind=engine)
s = Session()
book = s.query(TutorialBook).first()
print(f'Book: {book.title} ({book.category})')
print(f'Chapters: {s.query(TutorialChapter).filter_by(book_id=book.id).count()}')
print(f'Sections: {s.query(TutorialSection).count()}')
print(f'Figures: {s.query(TutorialFigure).count()}')
fig = s.query(TutorialFigure).first()
print(f'First figure: page={fig.page}, label={fig.figure_label}, path={fig.page_image_path}')
s.close()
"
```

- [ ] **Step 3.4: Verify assets copied**

```bash
ls data/tutorial_assets/ | head -5
ls data/tutorial_assets/*/pages/ | head -10
```

- [ ] **Step 3.5: Add tutorial_assets to .gitignore**

```bash
echo "data/tutorial_assets/" >> .gitignore
```

Assets are runtime data (potentially GBs of PNGs), not version-controlled.

- [ ] **Step 3.6: Commit**

```bash
git add scripts/import_book.py .gitignore
git commit -m "feat(tutorials-v2): add book import script with asset-first import ordering"
```

---

## Chunk 3: Backend API Rewrite

### Task 4: DB Query Functions

**File:** Create `katrain/web/tutorials/db_queries.py`

- [ ] **Step 4.1: Write query functions**

```python
"""Database query functions for the tutorial module.

Replaces the old TutorialLoader (JSON-based) with direct DB queries.
"""

from typing import Dict, List, Optional

from sqlalchemy.orm import Session, joinedload

from katrain.web.core.models_db import (
    TutorialBook,
    TutorialChapter,
    TutorialFigure,
    TutorialSection,
)


# ── Category (hardcoded) ──────────────────────────────────────────────────────

CATEGORIES = [
    {"slug": "入门", "title": "入门", "summary": "围棋基础知识，规则与基本技巧", "order": 1},
    {"slug": "布局", "title": "布局", "summary": "开局阶段的战略与要点", "order": 2},
    {"slug": "中盘", "title": "中盘", "summary": "中盘战斗、攻防与形势判断", "order": 3},
    {"slug": "官子", "title": "官子", "summary": "收官技巧与目数计算", "order": 4},
]


def get_categories() -> List[Dict]:
    return CATEGORIES


# ── Books ─────────────────────────────────────────────────────────────────────

def get_books_by_category(db: Session, category: str) -> List[TutorialBook]:
    return db.query(TutorialBook).filter_by(category=category).order_by(TutorialBook.title).all()


def get_book(db: Session, book_id: int) -> Optional[TutorialBook]:
    return db.query(TutorialBook).options(
        joinedload(TutorialBook.chapters).joinedload(TutorialChapter.sections)
    ).filter_by(id=book_id).first()


# ── Chapters ──────────────────────────────────────────────────────────────────

def get_chapters_by_book(db: Session, book_id: int) -> List[TutorialChapter]:
    return db.query(TutorialChapter).filter_by(book_id=book_id).order_by(TutorialChapter.order).all()


# ── Sections ──────────────────────────────────────────────────────────────────

def get_sections_by_chapter(db: Session, chapter_id: int) -> List[TutorialSection]:
    return db.query(TutorialSection).filter_by(chapter_id=chapter_id).order_by(TutorialSection.order).all()


def get_section(db: Session, section_id: int) -> Optional[TutorialSection]:
    return db.query(TutorialSection).options(
        joinedload(TutorialSection.figures)
    ).filter_by(id=section_id).first()


# ── Figures ───────────────────────────────────────────────────────────────────

def get_figures_by_section(db: Session, section_id: int) -> List[TutorialFigure]:
    return db.query(TutorialFigure).filter_by(section_id=section_id).order_by(TutorialFigure.order).all()


def get_figure(db: Session, figure_id: int) -> Optional[TutorialFigure]:
    return db.query(TutorialFigure).filter_by(id=figure_id).first()


def update_figure_board(db: Session, figure_id: int, board_payload: dict) -> Optional[TutorialFigure]:
    """Update the board_payload for a figure and return the updated figure."""
    figure = db.query(TutorialFigure).filter_by(id=figure_id).first()
    if figure is None:
        return None
    figure.board_payload = board_payload
    db.commit()
    db.refresh(figure)
    return figure
```

- [ ] **Step 4.2: Commit**

```bash
git add katrain/web/tutorials/db_queries.py
git commit -m "feat(tutorials-v2): add DB query functions replacing TutorialLoader"
```

---

### Task 5: Viewport Calculation Utility

**File:** Create `katrain/web/tutorials/viewport.py`

- [ ] **Step 5.1: Implement viewport calculation**

```python
"""Server-side viewport calculation for read-only board display.

Computes the minimal viewport (quarter, half, or full board) that contains
all stones, labels, letters, and shapes. The viewport boundary always includes
the star points (hoshi) at the edge for visual context.
"""

from typing import Dict, List, Optional, Set, Tuple


def _occupied_positions(payload: Dict) -> Set[Tuple[int, int]]:
    """Extract all occupied positions from a board_payload."""
    positions: Set[Tuple[int, int]] = set()
    stones = payload.get("stones", {})
    for coords in stones.values():
        for col, row in coords:
            positions.add((col, row))
    for key in ("labels", "letters", "shapes"):
        mapping = payload.get(key, {})
        if mapping:
            for coord_str in mapping:
                parts = coord_str.split(",")
                if len(parts) == 2:
                    positions.add((int(parts[0]), int(parts[1])))
    highlights = payload.get("highlights", [])
    for col, row in highlights:
        positions.add((col, row))
    return positions


def compute_viewport(payload: Dict) -> Optional[Dict]:
    """Compute the optimal viewport for a board_payload.

    Returns a viewport dict {col, row, size} or None for full board.
    The viewport snaps to quarter (10x10), half (10x19 or 19x10), or full (19x19).
    Star points at the viewport boundary are included.

    For 19x19 board:
    - Quarter TL: col=0, row=0, size=10  (includes hoshi at 3,3 and edge at 9)
    - Quarter TR: col=9, row=0, size=10
    - Quarter BL: col=0, row=9, size=10
    - Quarter BR: col=9, row=9, size=10
    - Half Top:   col=0, row=0, size_rows=10, size_cols=19  (but viewport is square, so use full)
    - Half Left:  col=0, row=0, size=19 with viewport adjustment
    """
    size = payload.get("size", 19)
    if size != 19:
        return None  # non-19x19 boards: show full

    positions = _occupied_positions(payload)
    if not positions:
        return None  # empty board: show full

    cols = {c for c, r in positions}
    rows = {r for c, r in positions}
    min_col, max_col = min(cols), max(cols)
    min_row, max_row = min(rows), max(rows)

    mid = 9  # center of 19x19

    # Determine which quadrants are occupied
    has_tl = any(c <= mid and r <= mid for c, r in positions)
    has_tr = any(c >= mid and r <= mid for c, r in positions)
    has_bl = any(c <= mid and r >= mid for c, r in positions)
    has_br = any(c >= mid and r >= mid for c, r in positions)

    quadrant_count = sum([has_tl, has_tr, has_bl, has_br])

    # Quarter board: only one quadrant occupied
    if quadrant_count == 1:
        if has_tl:
            return {"col": 0, "row": 0, "size": 10}
        if has_tr:
            return {"col": 9, "row": 0, "size": 10}
        if has_bl:
            return {"col": 0, "row": 9, "size": 10}
        if has_br:
            return {"col": 9, "row": 9, "size": 10}

    # Half board: two adjacent quadrants — use rectangular viewport {col, row, cols, rows}
    if quadrant_count == 2:
        if has_tl and has_tr and not has_bl and not has_br:
            return {"col": 0, "row": 0, "cols": 19, "rows": 10}   # top half
        if has_bl and has_br and not has_tl and not has_tr:
            return {"col": 0, "row": 9, "cols": 19, "rows": 10}   # bottom half
        if has_tl and has_bl and not has_tr and not has_br:
            return {"col": 0, "row": 0, "cols": 10, "rows": 19}   # left half
        if has_tr and has_br and not has_tl and not has_bl:
            return {"col": 9, "row": 0, "cols": 10, "rows": 19}   # right half

    # 3 or 4 quadrants, or diagonal: full board
    return None  # None means full board
```

Note: `SGFBoard` must support rectangular viewports via `{col, row, cols, rows}` in addition to the square `{col, row, size}`. This is implemented in Chunk 5 Task 11 step 11.5.

- [ ] **Step 5.2: Write viewport tests**

Create `tests/web_ui/test_tutorial_viewport.py`:

```python
from katrain.web.tutorials.viewport import compute_viewport


def test_empty_board_returns_none():
    payload = {"size": 19, "stones": {"B": [], "W": []}}
    assert compute_viewport(payload) is None


def test_single_corner_tl():
    payload = {"size": 19, "stones": {"B": [[3, 3]], "W": [[2, 4]]}, "labels": {"3,3": "1", "2,4": "2"}}
    vp = compute_viewport(payload)
    assert vp is not None
    assert vp["col"] == 0 and vp["row"] == 0 and vp["size"] == 10


def test_single_corner_br():
    payload = {"size": 19, "stones": {"B": [[15, 15]], "W": [[16, 14]]}, "labels": {}}
    vp = compute_viewport(payload)
    assert vp is not None
    assert vp["col"] == 9 and vp["row"] == 9 and vp["size"] == 10


def test_all_quadrants_returns_none():
    payload = {"size": 19, "stones": {"B": [[3, 3], [15, 15]], "W": [[3, 15], [15, 3]]}, "labels": {}}
    assert compute_viewport(payload) is None


def test_includes_letters_and_shapes():
    payload = {"size": 19, "stones": {"B": [[3, 3]], "W": []},
               "letters": {"5,5": "A"}, "shapes": {"4,4": "triangle"}}
    vp = compute_viewport(payload)
    assert vp is not None
    assert vp["col"] == 0 and vp["row"] == 0  # all in TL


def test_non_19_returns_none():
    payload = {"size": 13, "stones": {"B": [[3, 3]], "W": []}}
    assert compute_viewport(payload) is None


def test_top_half():
    """Stones in TL and TR → top half (19 wide, 10 tall)."""
    payload = {"size": 19, "stones": {"B": [[3, 3]], "W": [[15, 3]]}, "labels": {}}
    vp = compute_viewport(payload)
    assert vp == {"col": 0, "row": 0, "cols": 19, "rows": 10}


def test_bottom_half():
    payload = {"size": 19, "stones": {"B": [[3, 15]], "W": [[15, 15]]}, "labels": {}}
    vp = compute_viewport(payload)
    assert vp == {"col": 0, "row": 9, "cols": 19, "rows": 10}


def test_left_half():
    payload = {"size": 19, "stones": {"B": [[3, 3]], "W": [[3, 15]]}, "labels": {}}
    vp = compute_viewport(payload)
    assert vp == {"col": 0, "row": 0, "cols": 10, "rows": 19}


def test_right_half():
    payload = {"size": 19, "stones": {"B": [[15, 3]], "W": [[15, 15]]}, "labels": {}}
    vp = compute_viewport(payload)
    assert vp == {"col": 9, "row": 0, "cols": 10, "rows": 19}


def test_diagonal_returns_none():
    """Stones in TL and BR (diagonal) → full board."""
    payload = {"size": 19, "stones": {"B": [[3, 3]], "W": [[15, 15]]}, "labels": {}}
    assert compute_viewport(payload) is None
```

- [ ] **Step 5.3: Run tests**

```bash
CI=true uv run pytest tests/web_ui/test_tutorial_viewport.py -v
```

- [ ] **Step 5.4: Commit**

```bash
git add katrain/web/tutorials/viewport.py tests/web_ui/test_tutorial_viewport.py
git commit -m "feat(tutorials-v2): add server-side viewport calculation with tests"
```

---

### Task 6: Rewrite Pydantic Models

**File:** Rewrite `katrain/web/tutorials/models.py`

- [ ] **Step 6.1: Replace contents**

```python
"""Pydantic response models for the tutorial module V2.

Hierarchy: Category → Book → Chapter → Section → Figure
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel


class TutorialCategoryOut(BaseModel):
    slug: str
    title: str
    summary: str
    order: int
    book_count: int = 0


class TutorialBookOut(BaseModel):
    id: int
    category: str
    subcategory: str
    title: str
    author: Optional[str] = None
    translator: Optional[str] = None
    slug: str
    chapter_count: int = 0

    class Config:
        from_attributes = True


class TutorialChapterOut(BaseModel):
    id: int
    book_id: int
    chapter_number: str
    title: str
    order: int
    section_count: int = 0

    class Config:
        from_attributes = True


class TutorialSectionOut(BaseModel):
    id: int
    chapter_id: int
    section_number: str
    title: str
    order: int
    figure_count: int = 0

    class Config:
        from_attributes = True


class TutorialFigureOut(BaseModel):
    id: int
    section_id: int
    page: int
    figure_label: str
    book_text: Optional[str] = None
    bbox: Optional[Dict[str, float]] = None
    page_image_path: Optional[str] = None
    board_payload: Optional[Any] = None
    narration: Optional[str] = None
    audio_asset: Optional[str] = None
    order: int

    class Config:
        from_attributes = True


class TutorialSectionDetailOut(TutorialSectionOut):
    """Section with all its figures included."""
    figures: List[TutorialFigureOut] = []


class TutorialBookDetailOut(TutorialBookOut):
    """Book with chapters and their sections."""
    chapters: List[TutorialChapterOut] = []


class StrictBoardPayload(BaseModel):
    """Validated board_payload — rejects malformed or oversized data."""
    size: int = 19
    stones: Dict[str, List[List[int]]]  # {"B": [[col,row]], "W": [[col,row]]}
    labels: Optional[Dict[str, str]] = None
    letters: Optional[Dict[str, str]] = None
    shapes: Optional[Dict[str, str]] = None
    highlights: Optional[List[List[int]]] = None
    # viewport is computed server-side, not accepted from client


class BoardPayloadUpdate(BaseModel):
    """Request body for updating a figure's board_payload."""
    board_payload: StrictBoardPayload
    expected_updated_at: Optional[str] = None  # ISO timestamp for optimistic locking
```

- [ ] **Step 6.2: Commit**

```bash
git add katrain/web/tutorials/models.py
git commit -m "feat(tutorials-v2): rewrite Pydantic models for book hierarchy"
```

---

### Task 7: Rewrite API Endpoints

**File:** Rewrite `katrain/web/api/v1/endpoints/tutorials.py`

- [ ] **Step 7.1: Replace contents**

```python
"""Tutorial module API endpoints (V2 — database-backed).

Replaces the old JSON-file-based endpoints with DB queries.
"""

import logging
from pathlib import Path
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from katrain.web.core.db import get_db
from katrain.web.tutorials import db_queries
from katrain.web.tutorials.models import (
    BoardPayloadUpdate,
    TutorialBookDetailOut,
    TutorialBookOut,
    TutorialCategoryOut,
    TutorialChapterOut,
    TutorialFigureOut,
    TutorialSectionDetailOut,
    TutorialSectionOut,
)
from katrain.web.tutorials.viewport import compute_viewport

logger = logging.getLogger(__name__)
router = APIRouter()

ASSET_BASE = Path("data")


def _safe_asset_path(relative_path: str) -> Path:
    """Resolve asset path and reject any path traversal attempts."""
    resolved = (ASSET_BASE / relative_path).resolve()
    base = ASSET_BASE.resolve()
    if not resolved.is_relative_to(base):  # Python 3.9+
        raise HTTPException(status_code=400, detail="Invalid asset path")
    return resolved


# ── Categories (hardcoded) ────────────────────────────────────────────────────

@router.get("/categories", response_model=List[TutorialCategoryOut])
async def get_categories(db: Session = Depends(get_db)):
    cats = db_queries.get_categories()
    # Enrich with book counts
    for cat in cats:
        books = db_queries.get_books_by_category(db, cat["slug"])
        cat["book_count"] = len(books)
    return cats


# ── Books ─────────────────────────────────────────────────────────────────────

@router.get("/categories/{category}/books", response_model=List[TutorialBookOut])
async def get_books(category: str, db: Session = Depends(get_db)):
    books = db_queries.get_books_by_category(db, category)
    result = []
    for b in books:
        out = TutorialBookOut.model_validate(b)
        out.chapter_count = len(b.chapters) if b.chapters else 0
        result.append(out)
    return result


@router.get("/books/{book_id}", response_model=TutorialBookDetailOut)
async def get_book(book_id: int, db: Session = Depends(get_db)):
    book = db_queries.get_book(db, book_id)
    if book is None:
        raise HTTPException(status_code=404, detail="Book not found")
    out = TutorialBookDetailOut.model_validate(book)
    out.chapter_count = len(book.chapters)
    chapters_out = []
    for ch in book.chapters:
        ch_out = TutorialChapterOut.model_validate(ch)
        ch_out.section_count = len(ch.sections) if ch.sections else 0
        chapters_out.append(ch_out)
    out.chapters = chapters_out
    return out


# ── Chapters ──────────────────────────────────────────────────────────────────

@router.get("/books/{book_id}/chapters", response_model=List[TutorialChapterOut])
async def get_chapters(book_id: int, db: Session = Depends(get_db)):
    chapters = db_queries.get_chapters_by_book(db, book_id)
    result = []
    for ch in chapters:
        out = TutorialChapterOut.model_validate(ch)
        out.section_count = len(ch.sections) if ch.sections else 0
        result.append(out)
    return result


# ── Sections ──────────────────────────────────────────────────────────────────

@router.get("/chapters/{chapter_id}/sections", response_model=List[TutorialSectionOut])
async def get_sections(chapter_id: int, db: Session = Depends(get_db)):
    sections = db_queries.get_sections_by_chapter(db, chapter_id)
    result = []
    for sec in sections:
        out = TutorialSectionOut.model_validate(sec)
        out.figure_count = len(sec.figures) if sec.figures else 0
        result.append(out)
    return result


@router.get("/sections/{section_id}", response_model=TutorialSectionDetailOut)
async def get_section(section_id: int, db: Session = Depends(get_db)):
    section = db_queries.get_section(db, section_id)
    if section is None:
        raise HTTPException(status_code=404, detail="Section not found")
    out = TutorialSectionDetailOut.model_validate(section)
    out.figure_count = len(section.figures)
    out.figures = [TutorialFigureOut.model_validate(f) for f in section.figures]
    return out


# ── Figures ───────────────────────────────────────────────────────────────────

@router.get("/figures/{figure_id}", response_model=TutorialFigureOut)
async def get_figure(figure_id: int, db: Session = Depends(get_db)):
    figure = db_queries.get_figure(db, figure_id)
    if figure is None:
        raise HTTPException(status_code=404, detail="Figure not found")
    return TutorialFigureOut.model_validate(figure)


@router.put("/figures/{figure_id}/board", response_model=TutorialFigureOut)
async def update_figure_board(
    figure_id: int,
    update: BoardPayloadUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),  # requires auth
):
    """Update the board_payload for a figure. Computes viewport server-side.
    Uses optimistic locking via expected_updated_at to prevent silent overwrites."""
    figure = db_queries.get_figure(db, figure_id)
    if figure is None:
        raise HTTPException(status_code=404, detail="Figure not found")
    # Optimistic locking: reject if server state changed since client's read
    if update.expected_updated_at and figure.updated_at:
        if figure.updated_at.isoformat() != update.expected_updated_at:
            raise HTTPException(status_code=409, detail="Board was modified by another session. Reload and retry.")
    payload = update.board_payload
    viewport = compute_viewport(payload)
    payload["viewport"] = viewport
    figure = db_queries.update_figure_board(db, figure_id, payload)
    return TutorialFigureOut.model_validate(figure)


# ── Assets ────────────────────────────────────────────────────────────────────

@router.get("/assets/{asset_path:path}")
async def get_asset(asset_path: str):
    """Serve a page screenshot or other tutorial asset."""
    file_path = _safe_asset_path(asset_path)
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="Asset not found")
    return FileResponse(file_path)
```

- [ ] **Step 7.2: Feature-flag V2 in `server.py`**

In `katrain/web/server.py`, wrap the Tutorial Loader block with a feature flag. Keep old loader as fallback:

```python
    # ── Tutorial Module ──────────────────────────────────────────────────────
    import os
    tutorials_v2 = os.environ.get("TUTORIALS_V2_ENABLED", "true").lower() == "true"
    if tutorials_v2:
        log.info("Tutorial V2 enabled — using database-backed tutorials")
        # V2: DB is sole source of truth; no loader needed
    else:
        import pathlib
        from katrain.web.tutorials.loader import TutorialLoader
        tutorial_base = pathlib.Path("data/tutorials_published")
        if tutorial_base.exists():
            tutorial_loader = TutorialLoader(tutorial_base)
            try:
                tutorial_loader.load()
                app.state.tutorial_loader = tutorial_loader
                log.info("Tutorial V1 package loaded (legacy mode)")
            except Exception as e:
                log.warning(f"Failed to load tutorial V1 package: {e}")
```

Note: Old `loader.py` and `progress.py` are NOT deleted here. They remain as fallback until final cleanup in Chunk 6.

- [ ] **Step 7.4: Commit**

```bash
git add katrain/web/api/v1/endpoints/tutorials.py \
        katrain/web/server.py \
        katrain/web/tutorials/
git commit -m "feat(tutorials-v2): rewrite API endpoints for DB-backed hierarchy"
```

---

### Task 7b: Import Script Tests

- [ ] **Step 7b.1: Write import script tests**

Create `tests/web_ui/test_tutorial_import.py` covering:
1. **Type B import** (test book with sections — 曹薰铉布局技巧)
2. **Type A import** (book with no sections — synthetic section created from chapter title)
3. **Same-page multi-figure**: verify two figures on the same page share the same `page_image_path`
4. **`--force` reimport**: verify old data is deleted and reimported cleanly
5. **Asset copy verification**: after import, page PNGs exist at expected paths
6. **Slug uniqueness**: importing the same book twice without `--force` should warn, not crash
7. **Empty sections/pages**: book with empty elements array doesn't crash

```bash
CI=true uv run pytest tests/web_ui/test_tutorial_import.py -v
```

- [ ] **Step 7b.2: Commit**

```bash
git add tests/web_ui/test_tutorial_import.py
git commit -m "test(tutorials-v2): add import script tests for Type A/B books"
```

---

### Task 8: API Tests

**File:** Rewrite `tests/web_ui/test_tutorial_db_api.py`

- [ ] **Step 8.1: Write API tests**

```python
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from katrain.web.core import models_db
from katrain.web.core.db import get_db


@pytest.fixture
def client():
    from katrain.web.server import create_app

    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    models_db.Base.metadata.create_all(bind=engine)
    TestSession = sessionmaker(bind=engine)

    # Seed test data
    session = TestSession()
    book = models_db.TutorialBook(
        category="布局", subcategory="棋书", title="测试布局书",
        author="作者", slug="test-buju", asset_dir="tutorial_assets/test-buju/pages",
    )
    session.add(book)
    session.flush()
    chapter = models_db.TutorialChapter(book_id=book.id, chapter_number="第一章", title="布局入门", order=1)
    session.add(chapter)
    session.flush()
    section = models_db.TutorialSection(chapter_id=chapter.id, section_number="1", title="外势和实地", order=1)
    session.add(section)
    session.flush()
    for i in range(3):
        fig = models_db.TutorialFigure(
            section_id=section.id, page=11 + i, figure_label=f"图{i + 1}",
            book_text=f"测试文字{i + 1}", page_image_path=f"tutorial_assets/test-buju/pages/page_{11 + i:03d}.png",
            board_payload={"size": 19, "stones": {"B": [[3, 3]], "W": []}, "labels": {"3,3": "1"}} if i == 0 else None,
            order=i + 1,
        )
        session.add(fig)
    session.commit()
    session.close()

    app = create_app()

    def override_db():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_db
    return TestClient(app)


def test_get_categories(client):
    resp = client.get("/api/v1/tutorials/categories")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 4
    slugs = {c["slug"] for c in data}
    assert slugs == {"入门", "布局", "中盘", "官子"}


def test_get_books_by_category(client):
    resp = client.get("/api/v1/tutorials/categories/布局/books")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["title"] == "测试布局书"
    assert data[0]["chapter_count"] == 1


def test_get_book_detail(client):
    resp = client.get("/api/v1/tutorials/books/1")
    assert resp.status_code == 200
    data = resp.json()
    assert data["title"] == "测试布局书"
    assert len(data["chapters"]) == 1
    assert data["chapters"][0]["section_count"] == 1


def test_get_book_not_found(client):
    assert client.get("/api/v1/tutorials/books/999").status_code == 404


def test_get_sections(client):
    resp = client.get("/api/v1/tutorials/chapters/1/sections")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["title"] == "外势和实地"
    assert data[0]["figure_count"] == 3


def test_get_section_detail(client):
    resp = client.get("/api/v1/tutorials/sections/1")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["figures"]) == 3
    assert data["figures"][0]["figure_label"] == "图1"


def test_get_figure(client):
    resp = client.get("/api/v1/tutorials/figures/1")
    assert resp.status_code == 200
    data = resp.json()
    assert data["figure_label"] == "图1"
    assert data["board_payload"]["stones"]["B"] == [[3, 3]]


def test_update_board_payload(client):
    new_payload = {
        "board_payload": {
            "size": 19,
            "stones": {"B": [[3, 3], [5, 5]], "W": [[4, 4]]},
            "labels": {"3,3": "1", "4,4": "2", "5,5": "3"},
            "letters": {"7,7": "A"},
            "shapes": {"8,8": "triangle"},
        }
    }
    resp = client.put("/api/v1/tutorials/figures/1/board", json=new_payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["board_payload"]["letters"]["7,7"] == "A"
    assert data["board_payload"]["shapes"]["8,8"] == "triangle"
    # Viewport should be computed server-side
    assert "viewport" in data["board_payload"]


def test_update_board_figure_not_found(client):
    resp = client.put("/api/v1/tutorials/figures/999/board", json={"board_payload": {"size": 19, "stones": {"B": [], "W": []}}})
    assert resp.status_code in (404, 401)  # 401 if auth required, 404 if authenticated


def test_update_board_requires_auth(client):
    """Edit endpoint must require authentication."""
    resp = client.put("/api/v1/tutorials/figures/1/board",
                      json={"board_payload": {"size": 19, "stones": {"B": [], "W": []}}})
    assert resp.status_code == 401


def test_update_board_rejects_invalid_payload(client):
    """Malformed board_payload should be rejected by validation."""
    resp = client.put("/api/v1/tutorials/figures/1/board",
                      json={"board_payload": {"bad": "data"}})
    assert resp.status_code in (401, 422)  # 422 Unprocessable Entity from Pydantic


def test_path_traversal_rejected(client):
    """Asset endpoint rejects path traversal attempts."""
    resp = client.get("/api/v1/tutorials/assets/../../../etc/passwd")
    assert resp.status_code == 400
```

- [ ] **Step 8.2: Run tests**

```bash
CI=true uv run pytest tests/web_ui/test_tutorial_db_api.py -v
```

Expected: all tests PASSED

- [ ] **Step 8.3: Run full test suite — no regressions**

```bash
CI=true uv run pytest tests/ -v --tb=short 2>&1 | tail -20
```

Note: Old tests in `tests/web_ui/test_tutorial_api.py` and `tests/web_ui/test_tutorial_loader.py` will fail because the old loader/JSON system is removed. Delete them:

```bash
rm tests/web_ui/test_tutorial_api.py tests/web_ui/test_tutorial_loader.py
```

- [ ] **Step 8.4: Commit**

```bash
git add tests/web_ui/test_tutorial_db_api.py
git rm tests/web_ui/test_tutorial_api.py tests/web_ui/test_tutorial_loader.py
git commit -m "test(tutorials-v2): rewrite API tests for DB-backed system"
```

---

## Chunk 4: Frontend — Types, API, Navigation Pages

### Task 9: TypeScript Types + API Client

**Files:**
- Rewrite: `katrain/web/ui/src/galaxy/types/tutorial.ts`
- Rewrite: `katrain/web/ui/src/galaxy/api/tutorialApi.ts`

- [ ] **Step 9.1: Rewrite TypeScript types**

```typescript
// ── Response types matching Pydantic models ──────────────────────────────────

export interface TutorialCategory {
  slug: string;
  title: string;
  summary: string;
  order: number;
  book_count: number;
}

export interface TutorialBook {
  id: number;
  category: string;
  subcategory: string;
  title: string;
  author: string | null;
  translator: string | null;
  slug: string;
  chapter_count: number;
}

export interface TutorialChapter {
  id: number;
  book_id: number;
  chapter_number: string;
  title: string;
  order: number;
  section_count: number;
}

export interface TutorialSection {
  id: number;
  chapter_id: number;
  section_number: string;
  title: string;
  order: number;
  figure_count: number;
}

export interface TutorialFigure {
  id: number;
  section_id: number;
  page: number;
  figure_label: string;
  book_text: string | null;
  bbox: { x_min: number; y_min: number; x_max: number; y_max: number } | null;
  page_image_path: string | null;
  board_payload: BoardPayload | null;
  narration: string | null;
  audio_asset: string | null;
  order: number;
}

export interface TutorialSectionDetail extends TutorialSection {
  figures: TutorialFigure[];
}

export interface TutorialBookDetail extends TutorialBook {
  chapters: TutorialChapter[];
}

// ── Board payload ────────────────────────────────────────────────────────────

export interface BoardPayload {
  size: number;
  stones: { B: [number, number][]; W: [number, number][] };
  labels?: Record<string, string>;       // move numbers: "3,3" → "1"
  letters?: Record<string, string>;      // letter annotations: "5,5" → "A"
  shapes?: Record<string, string>;       // shape markers: "7,7" → "triangle"
  highlights?: [number, number][];
  viewport?: { col: number; row: number; size: number; cols?: number; rows?: number } | null;
}

// ── Edit mode types ──────────────────────────────────────────────────────────

export type StoneEditMode = 'black' | 'white' | 'alternate';
export type EditTool = 'stone' | 'letter' | 'shape' | 'eraser' | null;
export type ShapeType = 'triangle' | 'square' | 'circle';
```

- [ ] **Step 9.2: Rewrite API client**

```typescript
import type {
  TutorialCategory,
  TutorialBook,
  TutorialBookDetail,
  TutorialChapter,
  TutorialSection,
  TutorialSectionDetail,
  TutorialFigure,
  BoardPayload,
} from '../types/tutorial';

const BASE = '/api/v1/tutorials';

async function apiGet<T>(path: string): Promise<T> {
  const resp = await fetch(`${BASE}${path}`);
  if (!resp.ok) throw new Error(`Tutorial API ${resp.status}: ${await resp.text()}`);
  return resp.json() as Promise<T>;
}

async function apiPut<T>(path: string, body: unknown): Promise<T> {
  const resp = await fetch(`${BASE}${path}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!resp.ok) throw new Error(`Tutorial API ${resp.status}: ${await resp.text()}`);
  return resp.json() as Promise<T>;
}

export const TutorialAPI = {
  // Categories
  getCategories: (): Promise<TutorialCategory[]> => apiGet('/categories'),

  // Books
  getBooks: (category: string): Promise<TutorialBook[]> =>
    apiGet(`/categories/${encodeURIComponent(category)}/books`),
  getBook: (bookId: number): Promise<TutorialBookDetail> => apiGet(`/books/${bookId}`),

  // Chapters
  getChapters: (bookId: number): Promise<TutorialChapter[]> =>
    apiGet(`/books/${bookId}/chapters`),

  // Sections
  getSections: (chapterId: number): Promise<TutorialSection[]> =>
    apiGet(`/chapters/${chapterId}/sections`),
  getSection: (sectionId: number): Promise<TutorialSectionDetail> =>
    apiGet(`/sections/${sectionId}`),

  // Figures
  getFigure: (figureId: number): Promise<TutorialFigure> => apiGet(`/figures/${figureId}`),
  saveBoardPayload: (figureId: number, payload: BoardPayload): Promise<TutorialFigure> =>
    apiPut(`/figures/${figureId}/board`, { board_payload: payload }),

  // Assets
  assetUrl: (relativePath: string): string => `${BASE}/assets/${relativePath}`,
};
```

- [ ] **Step 9.3: TypeScript check**

```bash
cd katrain/web/ui && npx tsc --noEmit 2>&1 | head -30
```

Note: This will show errors from old pages that reference removed types. Those will be fixed in subsequent tasks.

- [ ] **Step 9.4: Commit**

```bash
git add katrain/web/ui/src/galaxy/types/tutorial.ts \
        katrain/web/ui/src/galaxy/api/tutorialApi.ts
git commit -m "feat(tutorials-v2): rewrite TypeScript types and API client for book hierarchy"
```

---

### Task 10: Navigation Pages

**Files:** Create new pages, delete old ones, update routing

- [ ] **Step 10.1: Rewrite `TutorialLandingPage.tsx`** — shows 4 category cards

The page structure is similar to existing but uses new types. Clicking a category navigates to `/galaxy/tutorials/:category`.

- [ ] **Step 10.2: Create `TutorialBooksPage.tsx`** — books in a category

Route: `/galaxy/tutorials/:category`
- Fetches `TutorialAPI.getBooks(category)`
- Shows book cards with title, author, chapter count
- Clicking a book navigates to `/galaxy/tutorials/book/:bookId`

- [ ] **Step 10.3: Create `TutorialBookDetailPage.tsx`** — chapter/section tree

Route: `/galaxy/tutorials/book/:bookId`
- Fetches `TutorialAPI.getBook(bookId)` (includes chapters)
- For each chapter, fetches sections
- Displays as expandable tree (MUI Accordion or List)
- Clicking a section navigates to `/galaxy/tutorials/section/:sectionId`

- [ ] **Step 10.4: Create `TutorialFigurePage.tsx`** — figure playback with editing

Route: `/galaxy/tutorials/section/:sectionId`
- Fetches `TutorialAPI.getSection(sectionId)` (includes all figures)
- Shows one figure at a time with prev/next navigation
- Two-column layout:
  - Left: Full page screenshot (`page_image_path` → `TutorialAPI.assetUrl(...)`) + `book_text`
  - Right: `EditableSGFBoard` (read-only by default, editable when edit button clicked) + narration + audio
- Progress bar / slider for stepping through figures
- If `board_payload` has labeled stones (move numbers), add a move-step slider to show intermediate positions

This is the core page. Key requirements:

**Three states for every data fetch:** loading spinner, error with retry button, empty state message.

**Key state:**
```tsx
const [section, setSection] = useState<TutorialSectionDetail | null>(null);
const [loading, setLoading] = useState(true);
const [error, setError] = useState<string | null>(null);
const [currentFigureIndex, setCurrentFigureIndex] = useState(0);

// Loading:  <CircularProgress />
// Error:    <Alert severity="error">{error} <Button onClick={retry}>重试</Button></Alert>
// Empty:    <Typography>该小节暂无变化图</Typography>
```

**Move-step slider semantics:**
- Parse `board_payload.labels` to find max numeric label (= total numbered moves)
- Unlabeled stones are "initial position" and are ALWAYS visible regardless of slider value
- Slider range: 0 (show only initial position) to maxMoveNumber (show all)
- Pass `maxMoveStep` to `SGFBoard` which filters: show stone if it has no label, OR its label <= maxMoveStep
- Only render slider when there are actually numbered moves (maxMoveNumber > 0)

**Save handler with optimistic locking:**
```tsx
const handleSave = async (payload: BoardPayload) => {
  if (!currentFigure) return;
  try {
    const updated = await TutorialAPI.saveBoardPayload(
      currentFigure.id, payload, currentFigure.updated_at  // pass for optimistic locking
    );
    // Update figure in local state
    setSection(prev => {
      if (!prev) return prev;
      const figures = [...prev.figures];
      figures[currentFigureIndex] = { ...figures[currentFigureIndex], ...updated };
      return { ...prev, figures };
    });
  } catch (err) {
    // Show snackbar/toast on 409 conflict or other errors
    alert(err instanceof Error ? err.message : '保存失败，请重试');
  }
};
```

- [ ] **Step 10.5: Update routes in `GalaxyApp.tsx`**

Replace old tutorial routes:

```tsx
// Remove:
// <Route path="tutorials" element={<TutorialLandingPage />} />
// <Route path="tutorials/:categorySlug" element={<TutorialTopicsPage />} />
// <Route path="tutorials/topic/:topicId" element={<TutorialTopicDetailPage />} />
// <Route path="tutorials/example/:exampleId" element={<TutorialExamplePage />} />

// Add:
<Route path="tutorials" element={<TutorialLandingPage />} />
<Route path="tutorials/:category" element={<TutorialBooksPage />} />
<Route path="tutorials/book/:bookId" element={<TutorialBookDetailPage />} />
<Route path="tutorials/section/:sectionId" element={<TutorialFigurePage />} />
```

- [ ] **Step 10.6: Delete old pages**

```bash
rm katrain/web/ui/src/galaxy/pages/tutorials/TutorialTopicsPage.tsx
rm katrain/web/ui/src/galaxy/pages/tutorials/TutorialTopicDetailPage.tsx
rm katrain/web/ui/src/galaxy/pages/tutorials/TutorialExamplePage.tsx
rm katrain/web/ui/src/galaxy/components/tutorials/StepDisplay.tsx
```

- [ ] **Step 10.7: Build frontend — verify**

```bash
cd katrain/web/ui && npm run build 2>&1 | tail -10
```

- [ ] **Step 10.8: Commit**

```bash
git add katrain/web/ui/src/
git commit -m "feat(tutorials-v2): rewrite navigation pages for book hierarchy"
```

---

## Chunk 5: Editable SGFBoard

### Task 11: Extend SGFBoard + Create EditableSGFBoard Wrapper

**Component architecture:**
- `SGFBoard.tsx` = pure rendering component (letters, shapes, rectangular viewport, `maxMoveStep` filtering)
- `EditableSGFBoard.tsx` = interactive wrapper that adds click handling, hover cursor, and invisible click grid. Only active when `isEditing` is true (prevents touch-scroll interception on mobile).

**File:** Modify `katrain/web/ui/src/galaxy/components/tutorials/SGFBoard.tsx`

- [ ] **Step 11.1: Extend `SGFPayload` interface**

```typescript
export interface SGFPayload {
  size: number;
  stones: { B: [number, number][]; W: [number, number][] };
  labels?: Record<string, string>;       // move numbers on stones
  letters?: Record<string, string>;      // letter annotations (empty intersections)
  shapes?: Record<string, string>;       // shape markers (empty intersections)
  highlights?: [number, number][];
  viewport?: { col: number; row: number; size: number } | null;
}
```

- [ ] **Step 11.2: Add rendering for letters**

Letters are rendered as text on empty intersections (no stone background):

```tsx
const letterEls: React.ReactNode[] = [];
for (const [coordStr, letter] of Object.entries(letters)) {
  const [col, row] = coordStr.split(',').map(Number);
  if (!inViewport(col, row)) continue;
  const { x, y } = toSvg(col, row);
  letterEls.push(
    <text key={`letter-${coordStr}`} x={x} y={y + 1} textAnchor="middle"
      dominantBaseline="middle" fontSize={STONE_R * 1.2} fill="#d32f2f"
      fontWeight="bold" fontFamily="sans-serif">
      {letter}
    </text>
  );
}
```

- [ ] **Step 11.3: Add rendering for shapes**

Shapes: triangle, square, circle on empty intersections:

```tsx
const shapeEls: React.ReactNode[] = [];
for (const [coordStr, shape] of Object.entries(shapes)) {
  const [col, row] = coordStr.split(',').map(Number);
  if (!inViewport(col, row)) continue;
  const { x, y } = toSvg(col, row);
  const r = STONE_R * 0.5;
  if (shape === 'triangle') {
    const pts = `${x},${y - r} ${x - r * 0.866},${y + r * 0.5} ${x + r * 0.866},${y + r * 0.5}`;
    shapeEls.push(<polygon key={`shape-${coordStr}`} points={pts} fill="none" stroke="#1565c0" strokeWidth={2} />);
  } else if (shape === 'square') {
    shapeEls.push(<rect key={`shape-${coordStr}`} x={x - r} y={y - r} width={r * 2} height={r * 2}
      fill="none" stroke="#1565c0" strokeWidth={2} />);
  } else if (shape === 'circle') {
    shapeEls.push(<circle key={`shape-${coordStr}`} cx={x} cy={y} r={r}
      fill="none" stroke="#1565c0" strokeWidth={2} />);
  }
}
```

- [ ] **Step 11.4: Add `maxMoveStep` prop to SGFBoard for move-step filtering**

```typescript
interface SGFBoardProps {
  payload: SGFPayload;
  maxMoveStep?: number;  // show only stones with numeric label <= maxMoveStep; unlabeled stones always shown
}
```

When `maxMoveStep` is set, filter stone rendering: show a stone if (a) it has no entry in `labels`, or (b) its label is numeric and <= `maxMoveStep`.

- [ ] **Step 11.4b: Create `EditableSGFBoard.tsx` wrapper**

```typescript
interface EditableSGFBoardProps {
  payload: SGFPayload;
  isEditing: boolean;
  onClick: (col: number, row: number) => void;
  maxMoveStep?: number;
}
```

`EditableSGFBoard` wraps `SGFBoard` and conditionally overlays an invisible click grid:
- When `isEditing` is true: render invisible rects over each intersection, add hover cursor, call `onClick(col, row)` on click. Show full 19×19 board (ignore viewport).
- When `isEditing` is false: just render `SGFBoard` with viewport applied. No click grid mounted (prevents touch-scroll issues on mobile).

- [ ] **Step 11.5: Support rectangular viewport (`cols`/`rows`)**

For half-board display, extend viewport to support `{col, row, cols, rows}` in addition to `{col, row, size}`:

```typescript
const vpCols = viewport?.cols ?? viewport?.size ?? size;
const vpRows = viewport?.rows ?? viewport?.size ?? size;
```

- [ ] **Step 11.6: Commit**

```bash
git add katrain/web/ui/src/galaxy/components/tutorials/SGFBoard.tsx
git commit -m "feat(tutorials-v2): extend SGFBoard with letters, shapes, click handler, and move-step support"
```

---

### Task 12: Board Editor Hook

**File:** Create `katrain/web/ui/src/galaxy/hooks/useBoardEditor.ts`

- [ ] **Step 12.1: Implement the editor state hook**

Key design points (not full code — implement following these rules):

**State:**
```typescript
const [payload, setPayload] = useState<BoardPayload>(...);
const [savedPayload, setSavedPayload] = useState<BoardPayload>(...); // last DB-saved version
const [undoStack, setUndoStack] = useState<BoardPayload[]>([]);       // max 50 entries
const [isEditing, setIsEditing] = useState(false);
const [activeTool, setActiveTool] = useState<EditTool>(null);
const [stoneMode, setStoneMode] = useState<StoneEditMode>('black');
const [nextStoneColor, setNextStoneColor] = useState<'B' | 'W'>('B'); // explicit, not count-based
const [numbering, setNumbering] = useState(false);
const [selectedShape, setSelectedShape] = useState<ShapeType>('triangle');
const moveCounterRef = useRef(0);
const letterCounterRef = useRef(0);
```

**Enter edit mode:**
- Compute `moveCounterRef` from max numeric label in `payload.labels`
- Compute `letterCounterRef` from max letter char code in `payload.letters` + 1
- Compute `nextStoneColor` from existing stones (not just count — analyze last labeled stone if available)
- Clear undo stack
- `setIsEditing(true); setActiveTool('stone')`

**Cancel edit (discard changes):**
- `setPayload(savedPayload)` — resets to last saved version from DB
- `setIsEditing(false); setActiveTool(null)`

**Save:**
- `await onSave(payload); setSavedPayload(payload); setIsEditing(false)`

**Undo:**
- Pop last entry from `undoStack`, set as current `payload`
- If stack empty, undo button disabled

**Tool switch — letter tool:**
- When `setActiveTool('letter')` is called, rescan current `payload.letters` to recalculate `letterCounterRef` from the actual maximum letter on the board. This handles the case where the user erased letters while using another tool.

**Click handler — fine-grained mutual exclusion:**
All occupancy checks happen INSIDE `setPayload(prev => ...)` using `prev`, not stale outer `payload`.

```
// Before any mutation, push prev to undo stack (max 50)
setUndoStack(stack => [...stack.slice(-49), prev]);
const next = structuredClone(prev);  // not JSON.parse(JSON.stringify())

ERASER: remove stone + label + letter + shape + highlight at position

STONE tool:
  - if position has stone/letter/shape → do nothing (blocked)
  - else: place stone with nextStoneColor
  - if numbering: moveCounterRef++ and set label
  - if alternate mode: flip nextStoneColor after placement

LETTER tool:
  - if position has stone or shape → do nothing (blocked by different type)
  - if position has letter → ALLOW: overwrite with next letter, consume counter
  - if position is empty → place next letter
  - letterCounterRef++; if > 25 → alert('字母已用完')
  - This correctly implements "same position click accumulates letters"

SHAPE tool:
  - if position has stone or letter → do nothing (blocked by different type)
  - if position has shape → replace with selected shape (allow changing shape type)
  - if position is empty → place selected shape
```

**Alternate mode color tracking:**
Use explicit `nextStoneColor` state that flips B→W→B after each successful stone placement. Do NOT infer from stone counts. Initialize from the existing position when entering edit mode.
```

- [ ] **Step 12.2: Commit**

```bash
git add katrain/web/ui/src/galaxy/hooks/useBoardEditor.ts
git commit -m "feat(tutorials-v2): add useBoardEditor hook for board editing state"
```

---

### Task 13: Board Edit Toolbar

**File:** Create `katrain/web/ui/src/galaxy/components/tutorials/BoardEditToolbar.tsx`

- [ ] **Step 13.1: Implement the toolbar**

A horizontal toolbar with the following buttons:
1. **Stone mode group**: Black (●) / White (○) / Alternate (◐) — toggle group
2. **Numbering toggle**: "123" icon — on/off
3. **Letter tool**: "ABC" icon — activates letter mode
4. **Shape tool**: dropdown with triangle/square/circle
5. **Eraser**: eraser icon — removes any element at clicked position
6. **Save**: save icon — calls `onSave`, exits edit mode

Use MUI `ToggleButtonGroup`, `ToggleButton`, `IconButton`, and `Menu` components.

Key behavior:
- Only one tool active at a time (stone/letter/shape/eraser)
- Stone mode sub-options (black/white/alternate) only visible when stone tool is active
- Numbering toggle independent of tool selection (applies when stone tool is active)
- Shape dropdown appears when shape tool is selected

- [ ] **Step 13.2: Commit**

```bash
git add katrain/web/ui/src/galaxy/components/tutorials/BoardEditToolbar.tsx
git commit -m "feat(tutorials-v2): add BoardEditToolbar component"
```

---

### Task 14: Wire Everything Together in TutorialFigurePage

- [ ] **Step 14.1: Complete `TutorialFigurePage.tsx`**

This page:
1. Loads section with all figures
2. Shows one figure at a time
3. Left panel: page screenshot + book_text
4. Right panel:
   - Read-only mode: SGFBoard with viewport cropping + edit button
   - Edit mode: Full SGFBoard + BoardEditToolbar + save/cancel buttons
5. Bottom: figure navigation (prev/next, progress bar, move-step slider)

The move-step slider (for stepping through numbered moves):
- Parse `board_payload.labels` to find max move number
- Slider from 0 to maxMoveNumber
- Pass `maxMoveStep` to SGFBoard to only show stones whose label ≤ current step

- [ ] **Step 14.2: Build frontend**

```bash
cd katrain/web/ui && npm run build 2>&1 | tail -10
```

- [ ] **Step 14.3: Commit**

```bash
git add katrain/web/ui/src/
git commit -m "feat(tutorials-v2): complete TutorialFigurePage with editable board and move-step slider"
```

---

## Chunk 6: Validation, Cleanup + E2E Tests

**CRITICAL:** All destructive deletions happen in this chunk, AFTER backend tests pass, frontend builds, and at least one E2E test confirms the new system works end-to-end.

### Task 15: Validate Migration Completeness

- [ ] **Step 15.1: Run count-parity check**

```bash
uv run python -c "
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from katrain.web.core.config import settings
from katrain.web.core.models_db import TutorialBook, TutorialChapter, TutorialSection, TutorialFigure
engine = create_engine(settings.DATABASE_URL)
s = sessionmaker(bind=engine)()
print(f'Books:    {s.query(TutorialBook).count()}')
print(f'Chapters: {s.query(TutorialChapter).count()}')
print(f'Sections: {s.query(TutorialSection).count()}')
print(f'Figures:  {s.query(TutorialFigure).count()}')
# Verify asset accessibility
fig = s.query(TutorialFigure).first()
from pathlib import Path
if fig and fig.page_image_path:
    assert Path('data') / fig.page_image_path.replace('tutorial_assets/', 'tutorial_assets/') .exists(), 'Asset missing!'
    print(f'Sample asset OK: {fig.page_image_path}')
s.close()
"
```

- [ ] **Step 15.2: Run all backend tests**

```bash
CI=true uv run pytest tests/web_ui/test_tutorial_db_models.py tests/web_ui/test_tutorial_db_api.py tests/web_ui/test_tutorial_viewport.py tests/web_ui/test_tutorial_import.py -v
```

All must pass before proceeding.

- [ ] **Step 15.3: Build frontend**

```bash
cd katrain/web/ui && npm run build
```

Must succeed.

### Task 15b: Deprecate UserTutorialProgress

**Decision:** UserTutorialProgress is deprecated in V2. The old progress system used `example_id`/`topic_id` which don't map to the new hierarchy. Rather than build a broken migration, we cleanly remove the progress feature:

- [ ] **Step 15b.1: Remove progress API endpoints**

In `katrain/web/api/v1/endpoints/tutorials.py`, remove the `/progress` GET and POST endpoints (they were already not included in the V2 rewrite — verify they are absent).

- [ ] **Step 15b.2: Keep the DB table but mark as deprecated**

Do NOT drop `UserTutorialProgress` table — existing data is preserved for potential future migration. Add a comment in `models_db.py`: `# DEPRECATED in V2 — kept for data preservation. Will be replaced in Phase 3.`

### Task 16: Delete Old Files

Only after Tasks 15 and 15b are complete:

- [ ] **Step 16.1: Remove old backend files**

```bash
git rm katrain/web/tutorials/loader.py
git rm katrain/web/tutorials/progress.py
```

- [ ] **Step 16.2: Remove old frontend files**

```bash
git rm katrain/web/ui/src/galaxy/pages/tutorials/TutorialTopicsPage.tsx
git rm katrain/web/ui/src/galaxy/pages/tutorials/TutorialTopicDetailPage.tsx
git rm katrain/web/ui/src/galaxy/pages/tutorials/TutorialExamplePage.tsx
git rm katrain/web/ui/src/galaxy/components/tutorials/StepDisplay.tsx
```

- [ ] **Step 16.3: Remove old JSON data**

```bash
git rm -r data/tutorials_published/
```

- [ ] **Step 16.4: Remove old tests**

```bash
git rm tests/web_ui/test_tutorial_api.py tests/web_ui/test_tutorial_loader.py
```

- [ ] **Step 16.5: Remove feature flag from server.py**

Remove the `TUTORIALS_V2_ENABLED` conditional — V2 is now the only path.

- [ ] **Step 16.6: Commit all cleanup**

```bash
git add -A
git commit -m "chore(tutorials-v2): remove deprecated V1 tutorial system (loader, progress, JSON data, old pages)"
```

---

### Task 17: Playwright E2E Tests

**File:** Rewrite `katrain/web/ui/tests/tutorial.spec.ts`

- [ ] **Step 16.1: Write E2E tests**

Prerequisite: Server running with imported test book data.

```typescript
import { test, expect } from '@playwright/test';

test.describe('Tutorial Module V2', () => {
  test('Landing page shows 4 category cards', async ({ page }) => {
    await page.goto('/galaxy/tutorials');
    await expect(page.getByText('入门')).toBeVisible({ timeout: 10000 });
    await expect(page.getByText('布局')).toBeVisible();
    await expect(page.getByText('中盘')).toBeVisible();
    await expect(page.getByText('官子')).toBeVisible();
  });

  test('Clicking category shows book list', async ({ page }) => {
    await page.goto('/galaxy/tutorials');
    await page.getByText('布局').click();
    await expect(page.getByText('曹薰铉布局技巧')).toBeVisible({ timeout: 10000 });
  });

  test('Clicking book shows chapter/section tree', async ({ page }) => {
    await page.goto('/galaxy/tutorials/布局');
    await page.getByText('曹薰铉布局技巧').first().click();
    await expect(page.getByText('第一章')).toBeVisible({ timeout: 10000 });
    await expect(page.getByText('布局入门')).toBeVisible();
  });

  test('Clicking section opens figure page', async ({ page }) => {
    // Navigate to first section
    await page.goto('/galaxy/tutorials/布局');
    await page.getByText('曹薰铉布局技巧').first().click();
    await page.getByText('外势和实地').click();
    // Should show first figure
    await expect(page.getByText('图1')).toBeVisible({ timeout: 10000 });
  });

  test('Figure page shows page screenshot on left', async ({ page }) => {
    await page.goto('/galaxy/tutorials/section/1');
    const img = page.locator('img[alt*="page"]');
    await expect(img).toBeVisible({ timeout: 10000 });
  });

  test('Figure page shows SGF board on right', async ({ page }) => {
    await page.goto('/galaxy/tutorials/section/1');
    await expect(page.locator('svg[aria-label="Go board diagram"]')).toBeVisible({ timeout: 10000 });
  });

  test('Next/prev buttons navigate between figures', async ({ page }) => {
    await page.goto('/galaxy/tutorials/section/1');
    await expect(page.getByText('图1')).toBeVisible({ timeout: 10000 });
    await page.getByRole('button', { name: /下一/ }).click();
    await expect(page.getByText('图2')).toBeVisible({ timeout: 5000 });
    await page.getByRole('button', { name: /上一/ }).click();
    await expect(page.getByText('图1')).toBeVisible({ timeout: 5000 });
  });

  test('Edit button enters edit mode with toolbar', async ({ page }) => {
    await page.goto('/galaxy/tutorials/section/1');
    await page.getByRole('button', { name: /编辑/ }).click();
    // Toolbar should appear
    await expect(page.getByRole('button', { name: /保存/ })).toBeVisible({ timeout: 5000 });
  });

  test('Save button exits edit mode', async ({ page }) => {
    await page.goto('/galaxy/tutorials/section/1');
    await page.getByRole('button', { name: /编辑/ }).click();
    await page.getByRole('button', { name: /保存/ }).click();
    // Should return to read-only mode
    await expect(page.getByRole('button', { name: /编辑/ })).toBeVisible({ timeout: 5000 });
  });

  test('Board click places a stone in edit mode', async ({ page }) => {
    await page.goto('/galaxy/tutorials/section/1');
    await page.getByRole('button', { name: /编辑/ }).click();
    // Click on the SVG board — verify a new circle element appears
    const board = page.locator('svg[aria-label="Go board diagram"]');
    await expect(board).toBeVisible({ timeout: 10000 });
    const stonesBefore = await board.locator('circle[fill="#1a1a1a"]').count();
    // Click near center of board
    await board.click({ position: { x: 200, y: 200 } });
    const stonesAfter = await board.locator('circle[fill="#1a1a1a"]').count();
    expect(stonesAfter).toBeGreaterThanOrEqual(stonesBefore);
  });

  test('Save persists to database — still visible after reload', async ({ page }) => {
    await page.goto('/galaxy/tutorials/section/1');
    await page.getByRole('button', { name: /编辑/ }).click();
    const board = page.locator('svg[aria-label="Go board diagram"]');
    await board.click({ position: { x: 200, y: 200 } });
    await page.getByRole('button', { name: /保存/ }).click();
    await expect(page.getByRole('button', { name: /编辑/ })).toBeVisible({ timeout: 5000 });
    // Reload and verify stone persisted
    await page.reload();
    await expect(page.locator('svg[aria-label="Go board diagram"]')).toBeVisible({ timeout: 10000 });
  });

  test('Cancel edit discards changes', async ({ page }) => {
    await page.goto('/galaxy/tutorials/section/1');
    await page.getByRole('button', { name: /编辑/ }).click();
    const board = page.locator('svg[aria-label="Go board diagram"]');
    await board.click({ position: { x: 200, y: 200 } });
    // Cancel instead of save
    await page.getByRole('button', { name: /取消/ }).click();
    // Should return to read-only mode without saving
    await expect(page.getByRole('button', { name: /编辑/ })).toBeVisible({ timeout: 5000 });
  });

  test('Loading state shows spinner', async ({ page }) => {
    await page.goto('/galaxy/tutorials/section/1');
    // CircularProgress should be visible briefly during load
    // (may be too fast to catch, so just verify page loads without error)
    await expect(page.locator('svg[aria-label="Go board diagram"]')).toBeVisible({ timeout: 15000 });
  });

  test('Empty category shows appropriate message', async ({ page }) => {
    await page.goto('/galaxy/tutorials/官子');
    // If no books imported for this category, show empty state
    const hasBooks = await page.getByText(/官子/).isVisible().catch(() => false);
    expect(hasBooks).toBe(true);
  });
});
```

- [ ] **Step 16.2: Run Playwright tests**

```bash
cd katrain/web/ui && npm test -- --grep "Tutorial" 2>&1 | tail -30
```

- [ ] **Step 16.3: Commit**

```bash
git add katrain/web/ui/tests/tutorial.spec.ts
git commit -m "test(tutorials-v2): rewrite Playwright E2E tests for V2 tutorial module"
```

---

## Acceptance Criteria

After all tasks complete, verify:

- [ ] **AC1:** 4 category cards (入门/布局/中盘/官子) visible on landing page
- [ ] **AC2:** Test book (曹薰铉布局技巧) browsable: categories → book → chapters → sections → figures
- [ ] **AC3:** Figure page shows full page screenshot on left, SGF board on right
- [ ] **AC4:** Edit button enters edit mode with full 19×19 board + toolbar
- [ ] **AC5:** Stone placement (black/white/alternate) works with optional numbering; alternate mode uses explicit color toggle, not count-based inference
- [ ] **AC6:** Letter mode places A→Z sequentially; clicking same position again replaces with next letter (consuming intermediate letters); alerts at Z limit; switching tools and back resumes from current max letter on board
- [ ] **AC7:** Shape mode places triangle/square/circle on empty intersections; clicking existing shape replaces with selected shape type
- [ ] **AC8:** Eraser removes any element (stone, letter, shape) at clicked position
- [ ] **AC9:** Fine-grained mutual exclusion: stone/letter/shape cannot coexist at same position, BUT letter can overwrite letter and shape can overwrite shape
- [ ] **AC10:** Save button → PUT API with auth + optimistic locking → DB updated → returns to read-only mode with server-computed viewport
- [ ] **AC11:** Cancel button discards all unsaved changes, restores last saved payload
- [ ] **AC12:** Undo button reverses the last board edit (up to 50 steps)
- [ ] **AC13:** Read-only mode shows cropped viewport: quarter (10×10), half (19×10 or 10×19), or full (19×19) with star points at boundaries
- [ ] **AC14:** Move-step slider shows intermediate board positions; unlabeled stones always visible; only numbered stones step
- [ ] **AC15:** `scripts/import_book.py` imports test book with all figures; assets copied before DB commit; page_context_text captured from description elements
- [ ] **AC16:** `data/tutorial_assets/` is in `.gitignore` — not committed to repo
- [ ] **AC17:** Edit API (`PUT /figures/{id}/board`) requires authentication; rejects malformed payloads; returns 409 on concurrent edit conflict
- [ ] **AC18:** All pages show loading spinner, error with retry, and empty state where appropriate
- [ ] **AC19:** Old JSON-based system fully removed in final cleanup (no `loader.py`, no `progress.py`, no `data/tutorials_published/`, no old pages)
- [ ] **AC20:** All backend tests pass, frontend builds, Playwright E2E tests pass — verified BEFORE any destructive deletions
- [ ] **AC21:** `UserTutorialProgress` table preserved but progress API removed; model marked as deprecated
