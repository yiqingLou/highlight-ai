"""
Stats routes - /api/stats
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database import get_db
from app.models import Task, Highlight, Clip, Bgm
from app.schemas.stats import StatsResponse, TotalsBreakdown, TopHighlight

router = APIRouter()


@router.get("/", response_model=StatsResponse)
def get_stats(db: Session = Depends(get_db)):
    """Return aggregated statistics about the project."""

    total_tasks = db.query(Task).count()
    total_highlights = db.query(Highlight).count()
    total_clips = db.query(Clip).count()
    total_bgm = db.query(Bgm).count()

    tasks_by_status = {}
    for status in ["pending", "processing", "done", "failed"]:
        count = db.query(Task).filter(Task.status == status).count()
        if count > 0:
            tasks_by_status[status] = count

    total_duration_result = db.query(func.sum(Task.duration_sec)).scalar()
    total_duration_sec = total_duration_result if total_duration_result else 0

    avg_score_result = db.query(func.avg(Highlight.score)).scalar()
    avg_score = round(avg_score_result, 1) if avg_score_result else 0

    top_highlights = (
        db.query(Highlight)
        .order_by(Highlight.score.desc())
        .limit(3)
        .all()
    )

    return StatsResponse(
        totals=TotalsBreakdown(
            tasks=total_tasks,
            highlights=total_highlights,
            clips=total_clips,
            bgm_tracks=total_bgm,
        ),
        tasks_by_status=tasks_by_status,
        total_duration_sec=total_duration_sec,
        total_duration_human=f"{int(total_duration_sec // 60)} min {int(total_duration_sec % 60)} sec",
        avg_highlight_score=avg_score,
        top_highlights=[
            TopHighlight(id=h.id, label=h.label, score=h.score)
            for h in top_highlights
        ],
    )