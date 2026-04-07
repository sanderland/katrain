# Data Model Reference

## BoardPayload (tutorial_figures.board_payload)

```typescript
interface BoardPayload {
  size: number;                          // Always 19
  stones: {
    B: [number, number][];               // Black stones as [col, row]
    W: [number, number][];               // White stones as [col, row]
  };
  labels?: Record<string, string>;       // Move numbers: "3,3" → "1"
  letters?: Record<string, string>;      // Annotations: "9,2" → "A"
  shapes?: Record<string, string>;       // Markers: "7,7" → "triangle|square|circle"
  highlights?: [number, number][];       // Emphasized positions
  viewport?: {                           // Computed server-side
    col: number; row: number;
    cols?: number; rows?: number;
  };
}
```

Coordinates are 0-indexed `[col, row]` where `(0,0)` is top-left corner of the 19x19 board.

## RecognitionDebug (tutorial_figures.recognition_debug)

```python
{
  "human_verified": bool,
  "verified_at": "ISO datetime",
  "verified_by": "username",
  "bbox": {
    "method": "vllm|cv",
    "bbox": [x1, y1, x2, y2],
    "debug_image": "relative/path.png"
  },
  "region": {
    "method": "vllm|cv",
    "col_start": int,       # 0-based column of leftmost visible line
    "row_start": int,       # 0-based row of topmost visible line
    "confidence": float,
    "evidence": ["left_border", "stars=6", ...],
    "grid_rows": int,
    "grid_cols": int,
    "needs_vllm": bool
  },
  "cv_detection": {
    "spacing": float,       # Grid spacing in pixels
    "total_occupied": int,
    "confident_count": int,
    "ambiguous_count": int,
    "debug_image": "relative/path.png"
  },
  "classification": {
    "annotated_crop": "relative/path.png",
    "contact_sheet": "relative/path.png",
    "label_map": {"A": [col_idx, row_idx], ...},  # Local coords
    "confident_cv": {"A": "black", ...},
    "classifications": {"A": "black+1", ...}       # Final merged
  },
  "crop_image": "relative/path.png"
}
```

## TrainingSample (training_samples table)

```python
class TrainingSample(Base):
    id: int                    # Primary key
    figure_id: int             # FK → tutorial_figures.id
    patch_label: str           # "A", "B", "AA" (from contact sheet)
    local_col: int             # Column index in cropped diagram
    local_row: int             # Row index in cropped diagram
    global_col: int            # Column on full 19×19 board
    global_row: int            # Row on full 19×19 board
    patch_image_path: str      # Relative to data/ (e.g. "tutorial_assets/.../patches/A_2_4.png")
    base_type: str             # "black" | "white" | "empty"
    move_number: int | None    # 1-99 or null
    shape: str | None          # "triangle" | "square" | "circle" | null
    letter: str | None         # "A" | "B" | ... | null
    source: str                # "human" (from verified figures)
    book_slug: str             # Book identifier
    created_at: datetime
```

## TutorialFigure (tutorial_figures table)

Key fields for recognition:
- `id`: Primary key
- `section_id`: FK to sections
- `page`: Page number in book
- `figure_label`: "图1", "图2", etc.
- `page_image_path`: Path to page image (e.g. "tutorial_assets/{book}/pages/page_011.png")
- `board_payload`: JSON BoardPayload (ground truth after human verification)
- `recognition_debug`: JSON RecognitionDebug (pipeline output metadata)
- `updated_at`: Timestamp for optimistic locking

## Hierarchy

```
TutorialCategory (slug, title)
  └─ TutorialBook (id, title, author, slug)
       └─ TutorialChapter (id, chapter_number, title)
            └─ TutorialSection (id, section_number, title)
                 └─ TutorialFigure (id, figure_label, page, board_payload, recognition_debug)
                      └─ TrainingSample (id, patch_label, base_type, move_number, ...)
```
