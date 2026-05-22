"""
highlight-ai backend - now backed by a real SQLite database.

Run with: uvicorn app.main:app --reload --port 8000
"""

from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Task, Highlight, Bgm, Setting


app = FastAPI(
    title="highlight-ai API",
    description="AI-powered game highlight clipping tool",
    version="0.2.0",
)

# Allow frontend (localhost:3000) to call this backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def read_root():
    """Health check endpoint."""
    return {
        "name": "highlight-ai",
        "status": "running",
        "version": "0.2.0",
    }


@app.get("/api/hello")
def hello():
    """Test endpoint."""
    return {"message": "Hello from FastAPI + SQLite!"}


# ============================================
# Real database endpoints
# ============================================

@app.get("/api/highlights")
def get_highlights(db: Session = Depends(get_db)):
    """Return all highlights from the database."""
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


@app.get("/api/tasks")
def get_tasks(db: Session = Depends(get_db)):
    """Return all tasks from the database."""
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


@app.get("/api/settings")
def get_settings(db: Session = Depends(get_db)):
    """Return all user settings."""
    settings = db.query(Setting).all()
    return {
        "settings": {s.key: s.value for s in settings}
    }