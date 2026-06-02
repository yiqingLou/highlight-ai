"""
Tasks routes - /api/tasks/*

Endpoints:
  GET  /                              - List all tasks
  GET  /{id}                          - Get one task by ID (with related highlights)
  POST /                              - Create a new task (auto-extracts video metadata)
                                        Rejects duplicate file_path with 409 Conflict
  POST /{id}/extract-frames           - Trigger frame extraction in background
                                        Returns 202 Accepted immediately
                                        Status updates: pending -> processing -> done/failed
  GET  /{id}/frames                   - Query frame extraction status / count / paths
"""

from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import SessionLocal, get_db
from app.models import Task, Highlight
from app.schemas.task import TaskListResponse, TaskDetailResponse, TaskCreate
from app.services.video_processor import (
    extract_video_metadata,
    extract_frames,
    VideoProbeError,
)

router = APIRouter()


# ============================================
# Helper functions
# ============================================

def update_task_status(
    db: Session,
    task: Task,
    status: str,
    progress: int = None,
    error_message: str = None,
) -> None:
    """Update task status + commit immediately."""
    task.status = status
    if progress is not None:
        task.progress = progress
    if error_message is not None:
        task.error_message = error_message
    db.commit()


def _run_frame_extraction_in_background(task_id: int, fps: int) -> None:
    """
    Background worker that does the actual frame extraction.
    Opens its own DB session because the request's session is closed by the time this runs.
    """
    db = SessionLocal()
    try:
        task = db.query(Task).filter(Task.id == task_id).first()
        if task is None:
            return  # task disappeared, nothing to do

        BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
        frames_dir = BACKEND_DIR / "frames" / str(task_id)

        try:
            extract_frames(
                video_path=task.file_path,
                output_dir=str(frames_dir),
                fps=fps,
            )
        except FileNotFoundError as e:
            update_task_status(db, task, status="failed", error_message=str(e))
            return
        except FileExistsError as e:
            update_task_status(db, task, status="failed", error_message=str(e))
            return
        except VideoProbeError as e:
            update_task_status(db, task, status="failed", error_message=str(e))
            return

        update_task_status(db, task, status="done", progress=100)
    finally:
        db.close()


# ============================================
# GET endpoints
# ============================================

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
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

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


# ============================================
# POST endpoints
# ============================================

@router.post("/", response_model=TaskDetailResponse, status_code=201)
def create_task(task_data: TaskCreate, db: Session = Depends(get_db)):
    """Create a new task with automatic video metadata extraction."""
    existing = db.query(Task).filter(Task.file_path == task_data.file_path).first()
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Task already exists for this file_path (id={existing.id})",
        )

    try:
        metadata = extract_video_metadata(task_data.file_path)
    except FileNotFoundError:
        raise HTTPException(
            status_code=400,
            detail=f"Video file not found: {task_data.file_path}",
        )
    except VideoProbeError as e:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot read video metadata: {str(e)}",
        )

    new_task = Task(
        file_path=task_data.file_path,
        file_name=task_data.file_name,
        file_size=metadata["file_size"],
        duration_sec=metadata["duration_sec"],
        width=metadata["width"],
        height=metadata["height"],
        fps=metadata["fps"],
        game_type=task_data.game_type,
        status="pending",
        progress=0,
    )

    db.add(new_task)
    db.commit()
    db.refresh(new_task)

    return TaskDetailResponse(
        id=new_task.id,
        file_name=new_task.file_name,
        file_path=new_task.file_path,
        file_size=new_task.file_size,
        duration_sec=new_task.duration_sec,
        width=new_task.width,
        height=new_task.height,
        fps=new_task.fps,
        game_type=new_task.game_type,
        status=new_task.status,
        progress=new_task.progress,
        error_message=new_task.error_message,
        highlight_count=0,
        highlight_ids=[],
    )


@router.post("/{task_id}/extract-frames", status_code=202)
def extract_task_frames(
    task_id: int,
    background_tasks: BackgroundTasks,
    fps: int = 1,
    db: Session = Depends(get_db),
):
    """
    Trigger frame extraction in the background.

    Returns 202 Accepted immediately with status="processing".
    The actual extraction runs asynchronously.
    Poll GET /api/tasks/{id} or GET /api/tasks/{id}/frames to check progress.

    Errors:
        404 if task not found
        409 if task already running or done (status != pending/failed)
    """
    # 1. Find the task
    task = db.query(Task).filter(Task.id == task_id).first()
    if task is None:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

    # 2. Reject if currently processing (idempotency guard)
    if task.status == "processing":
        raise HTTPException(
            status_code=409,
            detail=f"Task {task_id} is already being processed",
        )

    # 3. Mark as processing, then enqueue background task
    update_task_status(db, task, status="processing", progress=10)
    background_tasks.add_task(_run_frame_extraction_in_background, task_id, fps)

    return {
        "task_id": task_id,
        "status": "processing",
        "message": "Frame extraction started in background. Poll for status.",
        "fps": fps,
    }


@router.get("/{task_id}/frames")
def get_task_frames(task_id: int, db: Session = Depends(get_db)):
    """Get frame extraction status + sample paths for a task."""
    task = db.query(Task).filter(Task.id == task_id).first()
    if task is None:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

    BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
    frames_dir = BACKEND_DIR / "frames" / str(task_id)

    if not frames_dir.exists():
        return {
            "task_id": task_id,
            "task_status": task.status,
            "task_progress": task.progress,
            "extracted": False,
            "frame_count": 0,
            "frames_dir": str(frames_dir),
            "sample_paths": [],
        }

    frame_files = sorted(frames_dir.glob("frame_*.jpg"))

    return {
        "task_id": task_id,
        "task_status": task.status,
        "task_progress": task.progress,
        "extracted": len(frame_files) > 0,
        "frame_count": len(frame_files),
        "frames_dir": str(frames_dir),
        "sample_paths": [str(f) for f in frame_files[:3]],
    }