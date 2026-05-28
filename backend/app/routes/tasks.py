"""
Tasks routes - /api/tasks/*

Endpoints:
  GET  /                              - List all tasks
  GET  /{id}                          - Get one task by ID (with related highlights)
  POST /                              - Create a new task (auto-extracts video metadata)
  POST /{id}/extract-frames           - Extract JPG frames from task's video
"""

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Task, Highlight
from app.schemas.task import TaskListResponse, TaskDetailResponse, TaskCreate
from app.services.video_processor import (
    extract_video_metadata,
    extract_frames,
    VideoProbeError,
)

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


@router.post("/", response_model=TaskDetailResponse, status_code=201)
def create_task(task_data: TaskCreate, db: Session = Depends(get_db)):
    """
    Create a new task with automatic video metadata extraction.

    Required fields:
    - file_path: full path to video file on disk
    - file_name: filename for display

    Backend auto-extracts (overrides any user-provided values):
    - duration_sec, width, height, fps, file_size

    User-provided:
    - game_type (optional, must be set by user)

    Errors:
    - 400 if the file doesn't exist or isn't a valid video
    """
    # Auto-extract metadata from the video file using ffprobe
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

    # Create Task ORM object (auto-extracted fields take priority)
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


@router.post("/{task_id}/extract-frames")
def extract_task_frames(task_id: int, fps: int = 1, db: Session = Depends(get_db)):
    """
    Extract frames from a task's video file using ffmpeg.

    Path param:
        task_id: ID of the task to extract frames for

    Query param:
        fps: Frames per second to extract (default 1)

    Returns:
        task_id, frame_count, frames_dir, fps, sample_paths

    Errors:
        404 if task not found
        400 if video file missing or ffmpeg fails
        409 if frames already extracted for this task
    """
    # 1. Find the task
    task = db.query(Task).filter(Task.id == task_id).first()
    if task is None:
        raise HTTPException(
            status_code=404,
            detail=f"Task {task_id} not found",
        )

    # 2. Decide where to store frames: backend/frames/{task_id}/
    BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
    frames_dir = BACKEND_DIR / "frames" / str(task_id)

    # 3. Run extraction
    try:
        frame_paths = extract_frames(
            video_path=task.file_path,
            output_dir=str(frames_dir),
            fps=fps,
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except FileExistsError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except VideoProbeError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {
        "task_id": task_id,
        "frame_count": len(frame_paths),
        "frames_dir": str(frames_dir),
        "fps": fps,
        "sample_paths": frame_paths[:3],  # first 3 paths for verification
    }
@router.get("/{task_id}/frames")
def get_task_frames(task_id: int, db: Session = Depends(get_db)):
    """
    Get frame extraction status for a task.

    Returns whether frames have been extracted, count, and sample paths.

    Errors:
        404 if task not found
    """
    # 1. Verify task exists
    task = db.query(Task).filter(Task.id == task_id).first()
    if task is None:
        raise HTTPException(
            status_code=404,
            detail=f"Task {task_id} not found",
        )

    # 2. Check if frames directory exists
    BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
    frames_dir = BACKEND_DIR / "frames" / str(task_id)

    if not frames_dir.exists():
        return {
            "task_id": task_id,
            "extracted": False,
            "frame_count": 0,
            "frames_dir": str(frames_dir),
            "sample_paths": [],
        }

    # 3. Count and list frames
    frame_files = sorted(frames_dir.glob("frame_*.jpg"))

    return {
        "task_id": task_id,
        "extracted": len(frame_files) > 0,
        "frame_count": len(frame_files),
        "frames_dir": str(frames_dir),
        "sample_paths": [str(f) for f in frame_files[:3]],
    }