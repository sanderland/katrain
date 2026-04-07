#!/usr/bin/env python3
"""Export human-verified figures to training_samples table.

For each verified figure:
  1. Read board_payload (ground truth) + recognition_debug (label_map, patch paths)
  2. For each position in label_map:
     - Determine classification from board_payload (match global coordinates)
     - Find patch image in debug dir
     - Insert into training_samples table
  3. Skip figures already exported (idempotent)

Usage:
    python scripts/export_training_data.py [--section-id N] [--all] [--dry-run]
"""

import argparse
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from katrain.web.core.config import settings
from katrain.web.core.models_db import TrainingSample, TutorialFigure
from katrain.web.tutorials import db_queries

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger(__name__)

ASSET_BASE = Path("data")


def classify_position(board_payload, global_col, global_row):
    """Determine the classification of a position from board_payload (ground truth).

    Returns (base_type, move_number, shape, letter).
    """
    key = f"{global_col},{global_row}"

    # Check stones
    is_black = any(c == global_col and r == global_row for c, r in board_payload.get("stones", {}).get("B", []))
    is_white = any(c == global_col and r == global_row for c, r in board_payload.get("stones", {}).get("W", []))

    base_type = "black" if is_black else "white" if is_white else "empty"

    # Check labels (move numbers)
    move_number = None
    labels = board_payload.get("labels", {})
    if key in labels:
        try:
            move_number = int(labels[key])
        except (ValueError, TypeError):
            pass

    # Check shapes
    shape = board_payload.get("shapes", {}).get(key)

    # Check letters
    letter = board_payload.get("letters", {}).get(key)

    return base_type, move_number, shape, letter


def export_figure(db, figure, dry_run=False):
    """Export a single verified figure's patches to training_samples."""
    debug = figure.recognition_debug or {}
    payload = figure.board_payload or {}

    if not debug.get("human_verified"):
        return 0

    classification = debug.get("classification", {})
    label_map = classification.get("label_map", {})
    if not label_map:
        log.warning("  %s: no label_map in recognition_debug — skipping", figure.figure_label)
        return 0

    # Get region offset
    region = debug.get("region", {})
    col_start = region.get("col_start", 0)
    row_start = region.get("row_start", 0)

    # Derive book slug from page_image_path
    book_slug = ""
    if figure.page_image_path:
        parts = Path(figure.page_image_path).parts
        if len(parts) >= 2:
            book_slug = parts[1]  # tutorial_assets/{book_slug}/pages/...

    # Check for existing exports (idempotent)
    existing = db.query(TrainingSample).filter_by(figure_id=figure.id).count()
    if existing > 0:
        log.info("  %s: already exported (%d samples) — skipping", figure.figure_label, existing)
        return 0

    # Find patch images in debug dir
    debug_dir = ASSET_BASE / "tutorial_assets" / book_slug / "debug" / figure.figure_label / "patches"
    if not debug_dir.exists():
        # Try alternate location from --save-sheets
        debug_dir = ASSET_BASE / "tutorial_assets" / book_slug / "debug" / figure.figure_label
        # Patches might not be in a subdirectory
        if not debug_dir.exists():
            log.warning("  %s: no patch images found at %s — skipping", figure.figure_label, debug_dir)
            return 0

    samples = []
    for label, coords in label_map.items():
        local_col, local_row = coords[0], coords[1]
        global_col = col_start + local_col
        global_row = row_start + local_row

        # Find patch image
        patch_filename = f"{label}_{local_col}_{local_row}.png"
        patch_path = debug_dir / patch_filename
        if not patch_path.exists():
            # Try without subdirectory
            alt_path = debug_dir.parent / "patches" / figure.figure_label / patch_filename
            if alt_path.exists():
                patch_path = alt_path
            else:
                log.debug("  %s/%s: patch image not found", figure.figure_label, label)
                continue

        # Classify from ground truth board_payload
        base_type, move_number, shape, letter = classify_position(payload, global_col, global_row)

        relative_path = str(patch_path.relative_to(ASSET_BASE))

        sample = TrainingSample(
            figure_id=figure.id,
            patch_label=label,
            local_col=local_col,
            local_row=local_row,
            global_col=global_col,
            global_row=global_row,
            patch_image_path=relative_path,
            base_type=base_type,
            move_number=move_number,
            shape=shape,
            letter=letter,
            source="human",
            book_slug=book_slug,
        )
        samples.append(sample)

    if dry_run:
        for s in samples:
            label_str = f"{s.base_type}"
            if s.move_number:
                label_str += f"+{s.move_number}"
            if s.shape:
                label_str += f"({s.shape})"
            if s.letter:
                label_str += f"[{s.letter}]"
            log.info("  %s/%s: (%d,%d)→(%d,%d) = %s  img=%s",
                     figure.figure_label, s.patch_label,
                     s.local_col, s.local_row, s.global_col, s.global_row,
                     label_str, s.patch_image_path)
    else:
        db.add_all(samples)
        db.commit()

    log.info("  %s: exported %d training samples", figure.figure_label, len(samples))
    return len(samples)


def main():
    parser = argparse.ArgumentParser(description="Export verified figures to training_samples")
    parser.add_argument("--section-id", type=int, help="Export figures from this section")
    parser.add_argument("--all", action="store_true", help="Export all verified figures")
    parser.add_argument("--dry-run", action="store_true", help="Print samples without DB write")
    args = parser.parse_args()

    if not args.section_id and not args.all:
        parser.error("--section-id or --all required")

    engine = create_engine(settings.DATABASE_URL)
    Session = sessionmaker(bind=engine)
    db = Session()

    try:
        if args.all:
            # Query all figures with human_verified
            figures = db.query(TutorialFigure).filter(
                TutorialFigure.recognition_debug.isnot(None)
            ).all()
            figures = [f for f in figures if (f.recognition_debug or {}).get("human_verified")]
        else:
            section = db_queries.get_section(db, args.section_id)
            if section is None:
                log.error("Section %d not found", args.section_id)
                return
            figures = [f for f in section.figures if (f.recognition_debug or {}).get("human_verified")]

        log.info("Found %d verified figures", len(figures))

        total = 0
        for figure in sorted(figures, key=lambda f: f.id):
            count = export_figure(db, figure, dry_run=args.dry_run)
            total += count

        log.info("\nTotal: %d training samples exported to training_samples table", total)

        if not args.dry_run:
            # Print summary stats
            from collections import Counter
            counts = Counter()
            for s in db.query(TrainingSample).all():
                counts[s.base_type] += 1
            log.info("DB totals: %s", dict(counts))

    finally:
        db.close()


if __name__ == "__main__":
    main()
