"""
Highlights routes - /api/highlights/*

Endpoints:
  GET /         - List all highlights (sorted by score)
  GET /{id}     - Get one highlight by ID (with computed duration)
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Highlight
from app.schemas.highlight import (
    HighlightDetailResponse,
    HighlightListResponse,
)

# Create a router for highlights endpoints
router = APIRouter()


@router.get("/", response_model=HighlightListResponse)
def get_highlights(db: Session = Depends(get_db)):
    """Return all highlights, sorted by score (highest first)."""
    highlights = db.query(Highlight).order_by(Highlight.score.desc()).all()
    return {
        "highlights": highlights,
        "total": len(highlights),
    }


@router.get("/{highlight_id}", response_model=HighlightDetailResponse)
def get_highlight_by_id(highlight_id: int, db: Session = Depends(get_db)):
    """Return a single highlight by its ID, with detailed sub-scores."""
    highlight = db.query(Highlight).filter(Highlight.id == highlight_id).first()

    if highlight is None:
        raise HTTPException(
            status_code=404,
            detail=f"Highlight {highlight_id} not found",
        )

    return HighlightDetailResponse(
        id=highlight.id,
        task_id=highlight.task_id,
        label=highlight.label,
        start_sec=highlight.start_sec,
        end_sec=highlight.end_sec,
        duration_sec=round(highlight.end_sec - highlight.start_sec, 2),
        score=highlight.score,
        score_ocr=highlight.score_ocr,
        score_audio=highlight.score_audio,
        score_visual=highlight.score_visual,
        reason=highlight.reason,
        is_selected=highlight.is_selected,
        user_modified=highlight.user_modified,
    )