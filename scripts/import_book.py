#!/usr/bin/env python3
"""Import a Go book from book.json into the tutorial database.

Usage:
    python scripts/import_book.py \
        --book-dir /path/to/go-topic-collections/books/布局/曹薰铉布局技巧_上册_曹薰铉_1997 \
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

    slug = slugify(book_dir.name)

    existing = session.query(TutorialBook).filter_by(slug=slug).first()
    if existing:
        if force:
            log.info("Deleting existing book: %s (slug=%s)", title, slug)
            session.delete(existing)
            session.flush()
        else:
            log.warning("Book already imported: %s (slug=%s). Use --force to reimport.", title, slug)
            return existing

    # Copy page assets FIRST, before DB commit
    copied = copy_page_assets(book_dir, slug)
    if copied == 0:
        raise FileNotFoundError(f"No page images found in {book_dir / 'output' / 'pages'}")

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
    session.flush()

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
                    # Collect page-level context text
                    page_context_parts = []
                    for elem in page_data.get("elements", []):
                        if elem.get("type") == "description":
                            page_context_parts.append(elem.get("text", ""))

                    page_context_text = "\n".join(page_context_parts) if page_context_parts else None

                    for elem in page_data.get("elements", []):
                        if elem.get("type") != "figure_ref":
                            continue
                        fig_order += 1
                        figure = TutorialFigure(
                            section_id=section.id,
                            page=page_num,
                            figure_label=elem.get("label", f"图{fig_order}"),
                            book_text=elem.get("text", ""),
                            page_context_text=page_context_text,
                            bbox=elem.get("bbox"),
                            page_image_path=make_page_image_path(slug, page_num),
                            board_payload=None,
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
                page_context_parts = []
                for elem in page_data.get("elements", []):
                    if elem.get("type") == "description":
                        page_context_parts.append(elem.get("text", ""))
                page_context_text = "\n".join(page_context_parts) if page_context_parts else None

                for elem in page_data.get("elements", []):
                    if elem.get("type") != "figure_ref":
                        continue
                    fig_order += 1
                    figure = TutorialFigure(
                        section_id=section.id,
                        page=page_num,
                        figure_label=elem.get("label", f"图{fig_order}"),
                        book_text=elem.get("text", ""),
                        page_context_text=page_context_text,
                        bbox=elem.get("bbox"),
                        page_image_path=make_page_image_path(slug, page_num),
                        board_payload=None,
                        order=fig_order,
                    )
                    session.add(figure)
                    figure_count += 1

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
    parser.add_argument("--book-dir", type=Path, required=True, help="Path to book directory")
    parser.add_argument("--category", required=True, choices=sorted(VALID_CATEGORIES), help="Top-level category")
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
