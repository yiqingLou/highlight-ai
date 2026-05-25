"""
Tasks routes - /api/tasks/*

Endpoints:
  GET /         - List all tasks
  GET /{id}     - Get one task by ID (with related highlights)
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Task, Highlight
from app.schemas.task import TaskListResponse, TaskDetailResponse

router = APIRouter()


@router.get("/", response_model=TaskListResponse)
def get_tasks(db: Session = Depends(get_db)):
    """Return all tasks, sorted by most recent first."""
    tasks = db.query(Task).order_by(Task.created_at.desc()).all()
    return {
        "tasks": tasks,
        "total": len(tasks),
    }


@router.get("/{task_id}", response_model=TaskDetailResponse)
def get_task_by_id(task_id: int, db: Session = Depends(get_db)):
    """Return a single task with all its highlights."""
    task = db.query(Task).filter(Task.id == task_id).first()

    if task is None:
        raise HTTPException(
            status_code=404,
            detail=f"Task {task_id} not found",
        )

    # Get related highlights
    highlights = db.query(Highlight).filter(Highlight.task_id == task_id).all()

    return TaskDetailResponse(
        id=task.id,
        file_name=task.file_name,
        file_path=task.file_path,
        file_size=task.file_size,
        duration_sec=task.duration_sec,
        width=task.width,
        height=task.height,
        fps=task.fps,
        game_type=task.game_type,
        status=task.status,
        progress=task.progress,
        error_message=task.error_message,
        highlight_count=len(highlights),
        highlight_ids=[h.id for h in highlights],
    )