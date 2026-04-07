"""Prepare training data for EfficientNet-B0 patch classifier.

Reads manifest.jsonl or the training_samples DB table, deduplicates,
derives 8-class labels, organizes patches into class directories,
and generates train/val splits.

Usage:
    python scripts/prepare_training_data.py
    python scripts/prepare_training_data.py --from-db --val-ratio 0.2
    python scripts/prepare_training_data.py --data-dir data/training_patches --val-ratio 0.2
"""

import argparse
import json
import shutil
import sys
from collections import Counter
from pathlib import Path
from random import Random

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


CLASS_NAMES = [
    "black",
    "white",
    "black_numbered",
    "white_numbered",
    "marked_black",
    "marked_white",
    "letter",
    "empty",
]


DATA_BASE = Path(__file__).resolve().parent.parent / "data"


def load_entries_from_db() -> list[dict]:
    """Load human-verified training samples from the training_samples DB table.

    Returns entries in the same dict format as manifest entries:
    {"base_type", "text", "shape", "image_path"}.
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from katrain.web.core.config import settings
    from katrain.web.core.models_db import TrainingSample

    engine = create_engine(settings.DATABASE_URL)
    db = sessionmaker(bind=engine)()
    try:
        samples = db.query(TrainingSample).all()
        entries = []
        for s in samples:
            text = str(s.move_number) if s.move_number else (s.letter if s.letter else None)
            entries.append(
                {
                    "base_type": s.base_type,
                    "text": text,
                    "shape": s.shape,
                    "image_path": s.patch_image_path,  # relative to data/
                    "patch_id": f"db_{s.id}",
                }
            )
        return entries
    finally:
        db.close()


def derive_class(entry: dict) -> str:
    """Derive 8-class label from manifest entry fields."""
    base_type = entry.get("base_type", "empty")
    text = entry.get("text")
    shape = entry.get("shape")

    if shape:
        return f"marked_{base_type}" if base_type in ("black", "white") else "empty"
    if text and text.isdigit():
        return f"{base_type}_numbered" if base_type in ("black", "white") else "empty"
    if text and text.isalpha():
        return "letter"
    return base_type if base_type in ("black", "white", "empty") else "empty"


def main():
    parser = argparse.ArgumentParser(description="Prepare 8-class training data from manifest.jsonl or DB")
    parser.add_argument("--data-dir", type=Path, default=Path("data/training_patches"))
    parser.add_argument("--from-db", action="store_true", help="Read from training_samples DB table instead of manifest.jsonl")
    parser.add_argument("--val-ratio", type=float, default=0.2)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    prepared_dir = args.data_dir / "prepared"
    rng = Random(args.seed)

    if args.from_db:
        entries = load_entries_from_db()
        unique = entries  # DB entries are already unique (one row per sample)
        print(f"DB: {len(unique)} training samples loaded")
    else:
        manifest_path = args.data_dir / "manifest.jsonl"
        # Read and deduplicate manifest
        entries = []
        with open(manifest_path) as f:
            for line in f:
                line = line.strip()
                if line:
                    entries.append(json.loads(line))

        # Deduplicate by patch_id, keeping latest
        by_id = {}
        for e in entries:
            pid = e["patch_id"]
            if pid not in by_id or e.get("timestamp", "") > by_id[pid].get("timestamp", ""):
                by_id[pid] = e

        unique = list(by_id.values())
        print(f"Manifest: {len(entries)} entries → {len(unique)} unique patches")

    # Derive classes and filter patches with valid images
    classified = []
    missing = 0
    for e in unique:
        cls = derive_class(e)
        if args.from_db:
            img_path = DATA_BASE / e["image_path"]
        else:
            img_path = args.data_dir / e["image_path"]
        if not img_path.exists():
            missing += 1
            continue
        classified.append((e, cls, img_path))

    if missing:
        print(f"Warning: {missing} patches missing image files, skipped")

    # Create class directories
    for cls in CLASS_NAMES:
        (prepared_dir / cls).mkdir(parents=True, exist_ok=True)

    # Copy patches into class directories
    class_files = {cls: [] for cls in CLASS_NAMES}
    for e, cls, src_path in classified:
        dst_name = src_path.name
        dst_path = prepared_dir / cls / dst_name
        if not dst_path.exists() or src_path.stat().st_mtime > dst_path.stat().st_mtime:
            shutil.copy2(src_path, dst_path)
        rel_path = f"{cls}/{dst_name}"
        class_files[cls].append(rel_path)

    # Print distribution
    print(f"\n{'Class':<20} {'Count':>6}")
    print("-" * 28)
    total = 0
    for cls in CLASS_NAMES:
        count = len(class_files[cls])
        total += count
        bar = "#" * min(count, 50)
        print(f"{cls:<20} {count:>6}  {bar}")
    print("-" * 28)
    print(f"{'Total':<20} {total:>6}")

    # Stratified train/val split
    train_files = []
    val_files = []
    for cls in CLASS_NAMES:
        files = sorted(class_files[cls])
        rng.shuffle(files)
        n_val = max(1, int(len(files) * args.val_ratio)) if len(files) >= 2 else 0
        val_files.extend(files[:n_val])
        train_files.extend(files[n_val:])

    # Compute class weights (inverse frequency, normalized)
    class_counts = {cls: len(class_files[cls]) for cls in CLASS_NAMES}
    total_samples = sum(class_counts.values())
    n_classes = sum(1 for c in class_counts.values() if c > 0)
    class_weights = {}
    for cls in CLASS_NAMES:
        if class_counts[cls] > 0:
            class_weights[cls] = round(total_samples / (n_classes * class_counts[cls]), 4)
        else:
            class_weights[cls] = 0.0

    splits = {
        "train": sorted(train_files),
        "val": sorted(val_files),
        "class_names": CLASS_NAMES,
        "class_counts": class_counts,
        "class_weights": class_weights,
    }

    splits_path = prepared_dir / "splits.json"
    with open(splits_path, "w") as f:
        json.dump(splits, f, indent=2, ensure_ascii=False)

    print(f"\nTrain: {len(train_files)}, Val: {len(val_files)}")
    print(f"\nClass weights:")
    for cls in CLASS_NAMES:
        if class_counts[cls] > 0:
            print(f"  {cls:<20} {class_weights[cls]:.4f}")
    print(f"\nSplits saved to {splits_path}")


if __name__ == "__main__":
    main()
