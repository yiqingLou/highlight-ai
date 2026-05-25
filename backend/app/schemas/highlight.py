"""
Pydantic schemas for Highlight API responses.

These define the exact shape of data returned by /api/highlights endpoints.
"""

from pydantic import BaseModel
from typing import Optional


class HighlightResponse(BaseModel):
    """Compact highlight for list views (used by GET /api/highlights)."""
    id: int
    task_id: int
    label: Optional[str] = None
    start_sec: float
    end_sec: float
    score: Optional[int] = None
    reason: Optional[str] = None
    is_selected: bool = True

    class Config:
        # Allow Pydantic to read data from SQLAlchemy ORM objects
        from_attributes = True


class HighlightDetailResponse(BaseModel):
    """Detailed highlight (used by GET /api/highlights/{id})."""
    id: int
    task_id: int
    label: Optional[str] = None
    start_sec: float
    end_sec: float
    duration_sec: float
    score: Optional[int] = None
    score_ocr: Optional[int] = None
    score_audio: Optional[int] = None
    score_visual: Optional[int] = None
    reason: Optional[str] = None
    is_selected: bool = True
    user_modified: bool = False

    class Config:
        from_attributes = True


class HighlightListResponse(BaseModel):
    """Wrapper for list endpoint - includes total count."""
    highlights: list[HighlightResponse]
    total: int