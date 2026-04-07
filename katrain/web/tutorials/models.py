"""Pydantic response models for the tutorial module V2.

Hierarchy: Category → Book → Chapter → Section → Figure
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, field_validator, model_validator


class TutorialCategoryOut(BaseModel):
    slug: str
    title: str
    summary: str
    order: int
    book_count: int = 0


class TutorialBookOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    category: str
    subcategory: str
    title: str
    author: Optional[str] = None
    translator: Optional[str] = None
    slug: str
    chapter_count: int = 0


class TutorialChapterOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    book_id: int
    chapter_number: str
    title: str
    order: int
    section_count: int = 0


class TutorialSectionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    chapter_id: int
    section_number: str
    title: str
    order: int
    figure_count: int = 0


class TutorialFigureOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    section_id: int
    page: int
    figure_label: str
    book_text: Optional[str] = None
    page_context_text: Optional[str] = None
    bbox: Optional[Dict[str, float]] = None
    page_image_path: Optional[str] = None
    board_payload: Optional[Any] = None
    recognition_debug: Optional[Any] = None
    narration: Optional[str] = None
    audio_asset: Optional[str] = None
    video_asset: Optional[str] = None
    video_duration_ms: Optional[int] = None
    video_size_bytes: Optional[int] = None
    order: int
    updated_at: Optional[datetime] = None


class TutorialSectionDetailOut(TutorialSectionOut):
    """Section with all its figures included."""
    figures: List[TutorialFigureOut] = []


class TutorialBookDetailOut(TutorialBookOut):
    """Book with chapters and their sections."""
    chapters: List[TutorialChapterOut] = []


VALID_BOARD_SIZES = {9, 13, 19}


class StrictBoardPayload(BaseModel):
    """Validated board_payload — rejects malformed or oversized data."""
    size: int = 19
    stones: Dict[str, List[List[int]]]  # {"B": [[col,row]], "W": [[col,row]]}
    labels: Optional[Dict[str, str]] = None
    letters: Optional[Dict[str, str]] = None
    shapes: Optional[Dict[str, str]] = None
    highlights: Optional[List[List[int]]] = None
    # viewport is computed server-side, not accepted from client

    @field_validator("size")
    @classmethod
    def validate_size(cls, v: int) -> int:
        if v not in VALID_BOARD_SIZES:
            raise ValueError(f"size must be one of {sorted(VALID_BOARD_SIZES)}, got {v}")
        return v

    @model_validator(mode="after")
    def validate_coordinates(self) -> "StrictBoardPayload":
        max_coord = self.size - 1
        # Validate stones keys
        invalid_keys = set(self.stones.keys()) - {"B", "W"}
        if invalid_keys:
            raise ValueError(f"stones keys must be 'B' or 'W', got {invalid_keys}")
        # Validate stone coordinates
        for color, coords in self.stones.items():
            for pair in coords:
                if len(pair) != 2 or not (0 <= pair[0] <= max_coord and 0 <= pair[1] <= max_coord):
                    raise ValueError(f"stone coordinate {pair} out of bounds for size {self.size}")
        # Validate coordinate-keyed dicts (labels, letters, shapes)
        for field_name in ("labels", "letters", "shapes"):
            mapping = getattr(self, field_name)
            if not mapping:
                continue
            for key in mapping:
                parts = key.split(",")
                if len(parts) != 2:
                    raise ValueError(f"{field_name} key '{key}' must be 'col,row' format")
                col, row = int(parts[0]), int(parts[1])
                if not (0 <= col <= max_coord and 0 <= row <= max_coord):
                    raise ValueError(f"{field_name} coordinate '{key}' out of bounds for size {self.size}")
        # Validate highlights
        if self.highlights:
            for pair in self.highlights:
                if len(pair) != 2 or not (0 <= pair[0] <= max_coord and 0 <= pair[1] <= max_coord):
                    raise ValueError(f"highlight coordinate {pair} out of bounds for size {self.size}")
        return self


class BoardPayloadUpdate(BaseModel):
    """Request body for updating a figure's board_payload."""
    board_payload: StrictBoardPayload
    expected_updated_at: Optional[str] = None  # ISO timestamp for optimistic locking


class NarrationUpdate(BaseModel):
    """Request body for updating a figure's narration text and audio asset."""
    narration: str
    audio_asset: Optional[str] = None
    video_asset: Optional[str] = None
    video_duration_ms: Optional[int] = None
    video_size_bytes: Optional[int] = None
