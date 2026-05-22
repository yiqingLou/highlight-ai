"""
highlight-ai backend - powered by SQLite via SQLAlchemy.

Run with: uvicorn app.main:app --reload --port 8000

Available endpoints:
  GET  /                              - Health check
  GET  /api/hello                     - Test endpoint
  GET  /api/highlights                - List all highlights (sorted by score)
  GET  /api/highlights/{id}           - Get one highlight by ID (with computed duration)
  GET  /api/tasks                     - List all tasks
  GET  /api/tasks/{id}                - Get one task by ID (with related highlights)
  GET  /api/bgm                       - List all BGM tracks
  GET  /api/settings                  - All user settings as a dict
  GET  /api/stats                     - Aggregated project statistics
"""

from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database import get_db
from app.models import Task, Highlight, Clip, Bgm, Setting


app = FastAPI(
    title="highlight-ai API",
    description="AI-powered game highlight clipping tool",
    version="0.3.0",
)

# Allow frontend (localhost:3000) to call this backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================
# Health check
# ============================================

@app.get("/")
def read_root():
    """Health check endpoint."""
    return {
        "name": "highlight-ai",
        "status": "running",
        "version": "0.3.0",
    }


@app.get("/api/hello")
def hello():
    """Test endpoint."""
    return {"message": "Hello from FastAPI + SQLite!"}


# ============================================
# Highlights endpoints
# ============================================

@app.get("/api/highlights")
def get_highlights(db: Session = Depends(get_db)):
    """Return all highlights, sorted by score (highest first)."""
    highlights = db.query(Highlight).order_by(Highlight.score.desc()).all()
    return {
        "highlights": [
            {
                "id": h.id,
                "task_id": h.task_id,
                "label": h.label,
                "start_sec": h.start_sec,
                "end_sec": h.end_sec,
                "score": h.score,
                "reason": h.reason,
                "is_selected": h.is_selected,
            }
            for h in highlights
        ],
        "total": len(highlights),
    }


@app.get("/api/highlights/{highlight_id}")
def get_highlight_by_id(highlight_id: int, db: Session = Depends(get_db)):
    """Return a single highlight by its ID, with detailed sub-scores."""
    highlight = db.query(Highlight).filter(Highlight.id == highlight_id).first()

    if highlight is None:
        return {"error": "Highlight not found", "id": highlight_id}

    return {
        "id": highlight.id,
        "task_id": highlight.task_id,
        "label": highlight.label,
        "start_sec": highlight.start_sec,
        "end_sec": highlight.end_sec,
        "duration_sec": round(highlight.end_sec - highlight.start_sec, 2),
        "score": highlight.score,
        "score_ocr": highlight.score_ocr,
        "score_audio": highlight.score_audio,
        "score_visual": highlight.score_visual,
        "reason": highlight.reason,
        "is_selected": highlight.is_selected,
        "user_modified": highlight.user_modified,
    }


# ============================================
# Tasks endpoints
# ============================================

@app.get("/api/tasks")
def get_tasks(db: Session = Depends(get_db)):
    """Return all tasks, sorted by most recent first."""
    tasks = db.query(Task).order_by(Task.created_at.desc()).all()
    return {
        "tasks": [
            {
                "id": t.id,
                "file_name": t.file_name,
                "duration_sec": t.duration_sec,
                "status": t.status,
                "progress": t.progress,
                "game_type": t.game_type,
            }
            for t in tasks
        ],
        "total": len(tasks),
    }


@app.get("/api/tasks/{task_id}")
def get_task_by_id(task_id: int, db: Session = Depends(get_db)):
    """Return a single task with all its highlights."""
    task = db.query(Task).filter(Task.id == task_id).first()

    if task is None:
        return {"error": "Task not found", "id": task_id}

    # Get related highlights
    highlights = db.query(Highlight).filter(Highlight.task_id == task_id).all()

    return {
        "id": task.id,
        "file_name": task.file_name,
        "file_path": task.file_path,
        "file_size": task.file_size,
        "duration_sec": task.duration_sec,
        "width": task.width,
        "height": task.height,
        "fps": task.fps,
        "game_type": task.game_type,
        "status": task.status,
        "progress": task.progress,
        "error_message": task.error_message,
        # Computed fields
        "highlight_count": len(highlights),
        "highlight_ids": [h.id for h in highlights],
    }


# ============================================
# BGM endpoint
# ============================================

@app.get("/api/bgm")
def get_bgm(db: Session = Depends(get_db)):
    """Return all available BGM tracks."""
    bgm_list = db.query(Bgm).order_by(Bgm.sort_order).all()
    return {
        "bgm": [
            {
                "id": b.id,
                "name": b.name,
                "style": b.style,
                "duration_sec": b.duration_sec,
            }
            for b in bgm_list
        ],
        "total": len(bgm_list),
    }


# ============================================
# Settings endpoint
# ============================================

@app.get("/api/settings")
def get_settings(db: Session = Depends(get_db)):
    """Return all user settings as a key-value dict."""
    settings = db.query(Setting).all()
    return {
        "settings": {s.key: s.value for s in settings}
    }


# ============================================
# Stats endpoint (aggregated project statistics)
# ============================================

@app.get("/api/stats")
def get_stats(db: Session = Depends(get_db)):
    """Return aggregated statistics about the project."""

    # Count totals
    total_tasks = db.query(Task).count()
    total_highlights = db.query(Highlight).count()
    total_clips = db.query(Clip).count()
    total_bgm = db.query(Bgm).count()

    # Task status breakdown
    tasks_by_status = {}
    for status in ["pending", "processing", "done", "failed"]:
        count = db.query(Task).filter(Task.status == status).count()
        if count > 0:
            tasks_by_status[status] = count

    # Total duration processed (sum of all task durations)
    total_duration_result = db.query(func.sum(Task.duration_sec)).scalar()
    total_duration_sec = total_duration_result if total_duration_result else 0

    # Average highlight score
    avg_score_result = db.query(func.avg(Highlight.score)).scalar()
    avg_score = round(avg_score_result, 1) if avg_score_result else 0

    # Top 3 highlights by score
    top_highlights = (
        db.query(Highlight)
        .order_by(Highlight.score.desc())
        .limit(3)
        .all()
    )

    return {
        "totals": {
            "tasks": total_tasks,
            "highlights": total_highlights,
            "clips": total_clips,
            "bgm_tracks": total_bgm,
        },
        "tasks_by_status": tasks_by_status,
        "total_duration_sec": total_duration_sec,
        "total_duration_human": f"{int(total_duration_sec // 60)} min {int(total_duration_sec % 60)} sec",
        "avg_highlight_score": avg_score,
        "top_highlights": [
            {
                "id": h.id,
                "label": h.label,
                "score": h.score,
            }
            for h in top_highlights
        ],
    }