"""Database query functions for the tutorial module.

Replaces the old TutorialLoader (JSON-based) with direct DB queries.
"""

from typing import Dict, List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload, selectinload

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


def get_book_counts_by_category(db: Session) -> Dict[str, int]:
    """Return {category_slug: book_count} using a single COUNT+GROUP BY query."""
    rows = db.query(
        TutorialBook.category,
        func.count(TutorialBook.id),
    ).group_by(TutorialBook.category).all()
    return {category: count for category, count in rows}


# ── Books ─────────────────────────────────────────────────────────────────────

def get_books_by_category(db: Session, category: str) -> List[TutorialBook]:
    return db.query(TutorialBook).options(
        selectinload(TutorialBook.chapters)
    ).filter_by(category=category).order_by(TutorialBook.title).all()


def get_book(db: Session, book_id: int) -> Optional[TutorialBook]:
    return db.query(TutorialBook).options(
        joinedload(TutorialBook.chapters).joinedload(TutorialChapter.sections)
    ).filter_by(id=book_id).first()


# ── Chapters ──────────────────────────────────────────────────────────────────

def get_chapters_by_book(db: Session, book_id: int) -> List[TutorialChapter]:
    return db.query(TutorialChapter).options(
        selectinload(TutorialChapter.sections)
    ).filter_by(book_id=book_id).order_by(TutorialChapter.order).all()


# ── Sections ──────────────────────────────────────────────────────────────────

def get_sections_by_chapter(db: Session, chapter_id: int) -> List[TutorialSection]:
    return db.query(TutorialSection).options(
        selectinload(TutorialSection.figures)
    ).filter_by(chapter_id=chapter_id).order_by(TutorialSection.order).all()


def get_section(db: Session, section_id: int) -> Optional[TutorialSection]:
    return db.query(TutorialSection).options(
        joinedload(TutorialSection.figures)
    ).filter_by(id=section_id).first()


# ── Figures ───────────────────────────────────────────────────────────────────

def get_figures_by_section(db: Session, section_id: int) -> List[TutorialFigure]:
    return db.query(TutorialFigure).filter_by(section_id=section_id).order_by(TutorialFigure.order).all()


def get_figure(db: Session, figure_id: int) -> Optional[TutorialFigure]:
    return db.query(TutorialFigure).filter_by(id=figure_id).first()


def update_figure_board(db: Session, figure: TutorialFigure, board_payload: dict) -> TutorialFigure:
    """Update the board_payload on an already-fetched figure.

    Automatically computes and embeds the viewport if not already present.
    """
    from katrain.web.tutorials.viewport import compute_viewport

    # Compute viewport before writing (ensures consistent display)
    if "viewport" not in board_payload:
        board_payload["viewport"] = compute_viewport(board_payload)

    figure.board_payload = board_payload
    db.commit()
    db.refresh(figure)
    return figure


def update_figure_narration(db: Session, figure: TutorialFigure, narration: str, audio_asset: str | None) -> TutorialFigure:
    """Update narration text and audio_asset path on a figure."""
    figure.narration = narration
    if audio_asset is not None:
        figure.audio_asset = audio_asset
    db.commit()
    db.refresh(figure)
    return figure


def update_figure_recognition_debug(db: Session, figure: TutorialFigure, debug_data: dict) -> TutorialFigure:
    """Update the recognition_debug on an already-fetched figure."""
    figure.recognition_debug = debug_data
    db.commit()
    db.refresh(figure)
    return figure
