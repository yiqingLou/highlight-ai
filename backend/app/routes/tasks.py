"""
Tasks routes - /api/tasks/*

Endpoints:
  GET  /                              - List tasks (filter + paginate)
  GET  /{id}                          - Get one task by ID
  POST /                              - Create a new task (auto-extracts metadata)
  POST /{id}/extract-frames           - Trigger frame extraction (background, 202 Accepted)
  GET  /{id}/frames                   - Query frame extraction result
  GET  /{id}/progress                 - Real-time extraction progress
  POST /{id}/generate-clips           - Cut high-score highlights into clips (background, 202)
  GET  /{id}/clips                    - List generated clips for a task
"""

import json
import shutil
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import SessionLocal, get_db
from app.models import Task, Highlight, Clip
from app.schemas.task import TaskListResponse, TaskDetailResponse, TaskCreate
from app.services.video_processor import (
    extract_video_metadata,
    extract_frames,
    VideoProbeError,
)
from app.services.clip_assembler import cut_clip, get_clip_file_size
from app.game_profiles.base import get_profile

router = APIRouter()

# Only highlights scoring at/above this are cut into clips (i.e. multi-kills:
# double_kill=93, shutdown=95, triple_kill=96, quadra=98, penta=100).
# Plain single kills (90) are skipped to keep clips focused on the exciting moments.
MIN_CLIP_SCORE = 93

# Map a highlight kind -> score (0-100). Multi-kills outrank single kills, so
# the MIN_CLIP_SCORE gate naturally keeps only the exciting streaks. Unknown
# kinds fall back to the single-kill score.
KIND_SCORE = {
    "kill": 90,
    "double_kill": 93,
    "triple_kill": 96,
    "quadra_kill": 98,
    "penta_kill": 100,
}


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


def _clear_frames_dir(frames_dir: Path) -> None:
    """
    Safely remove an existing per-task frames directory before re-extracting.

    This makes re-running extraction idempotent: a previous run's frames no
    longer cause extract_frames() to fail on a non-empty directory.

    Safety: only ever deletes the specific per-task directory passed in.
    """
    # Guard: only delete if it exists and is a directory (never touch files).
    if frames_dir.exists() and frames_dir.is_dir():
        shutil.rmtree(frames_dir)


def _run_frame_extraction_in_background(task_id: int, fps: int) -> None:
    """
    Background worker: extract frames, then run highlight detection.

    Pipeline:
        0. Clear any existing frames for this task (idempotent re-runs)
        1. Extract frames from the video (ffmpeg)
        2. Load the game profile plugin for this task's game_type
        3. Detect highlights from the frames
        4. Store detected highlights in the DB
        5. Mark task as done

    Any failure marks the task as failed with an error message.
    """
    db = SessionLocal()
    try:
        task = db.query(Task).filter(Task.id == task_id).first()
        if task is None:
            return

        BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
        frames_dir = BACKEND_DIR / "frames" / str(task_id)

        # --- Step 0: clear old frames so re-runs start clean ---
        _clear_frames_dir(frames_dir)

        # --- Step 1: extract frames (capture the returned paths) ---
        try:
            frame_paths = extract_frames(
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

        # --- Step 2: load the game profile plugin ---
        try:
            profile = get_profile(task.game_type)
        except ValueError as e:
            # game_type not supported / not registered
            update_task_status(db, task, status="failed", error_message=str(e))
            return

        # --- Step 3: detect highlights ---
        # fps here is the extraction fps (frames sampled per second), which is
        # exactly what detect_highlights expects to convert frame index -> seconds.
        try:
            detected = profile.detect_highlights(frame_paths, fps=float(fps))
        except Exception as e:
            update_task_status(
                db, task, status="failed",
                error_message=f"Highlight detection failed: {e}",
            )
            return

        # --- Step 4: store detected highlights in the DB ---
        # Clear any existing highlights for this task first (idempotent re-runs).
        db.query(Highlight).filter(Highlight.task_id == task_id).delete()

        for sort_idx, dh in enumerate(detected):
            # Convert center + duration -> [start, end], clamp start at 0.
            start_sec = max(0.0, dh.center_sec - dh.duration_sec / 2)
            end_sec = dh.center_sec + dh.duration_sec / 2

            # Map highlight kind -> score (0-100). Multi-kills outrank singles.
            # Unknown kinds fall back to the single-kill score.
            score_100 = KIND_SCORE.get(dh.kind, 90)

            highlight = Highlight(
                task_id=task_id,
                start_sec=round(start_sec, 2),
                end_sec=round(end_sec, 2),
                score=score_100,
                score_visual=score_100,   # visual-based game, fill visual score
                label=dh.kind,
                reason=str(dh.meta),      # e.g. "{'source': 'yolo', 'kill_count': 2}"
                sort_order=sort_idx,
            )
            db.add(highlight)

        db.commit()

        # --- Step 5: mark task done ---
        update_task_status(db, task, status="done", progress=100)

    finally:
        db.close()


def _clear_clips_dir(clips_dir: Path) -> None:
    """
    Safely remove an existing per-task clips directory before regenerating.

    Makes re-running clip generation idempotent. Only ever deletes the
    specific per-task directory passed in.
    """
    if clips_dir.exists() and clips_dir.is_dir():
        shutil.rmtree(clips_dir)


def _run_clip_generation_in_background(task_id: int) -> None:
    """
    Background worker: cut high-score highlights into individual clip files.

    Pipeline:
        0. Clear any existing clips for this task (idempotent re-runs)
        1. Load the task's highlights scoring >= MIN_CLIP_SCORE
        2. Cut each one out of the source video with ffmpeg (one clip per highlight)
        3. Store each clip's metadata in the Clip table

    Errors on a single clip are skipped (best-effort), so one bad highlight
    does not abort the whole batch.
    """
    db = SessionLocal()
    try:
        task = db.query(Task).filter(Task.id == task_id).first()
        if task is None:
            return

        BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
        clips_dir = BACKEND_DIR / "clips" / str(task_id)

        # --- Step 0: clear old clips (DB rows + files) for clean re-runs ---
        db.query(Clip).filter(Clip.task_id == task_id).delete()
        db.commit()
        _clear_clips_dir(clips_dir)
        clips_dir.mkdir(parents=True, exist_ok=True)

        # --- Step 1: load high-score highlights, best first ---
        highlights = (
            db.query(Highlight)
            .filter(Highlight.task_id == task_id)
            .filter(Highlight.score >= MIN_CLIP_SCORE)
            .order_by(Highlight.score.desc())
            .all()
        )

        resolution = None
        if task.width and task.height:
            resolution = f"{task.width}x{task.height}"

        # --- Step 2 & 3: cut each highlight, store Clip row ---
        for idx, hl in enumerate(highlights):
            output_path = clips_dir / f"clip_{idx:03d}_{hl.label}.mp4"

            try:
                cut_clip(
                    video_path=task.file_path,
                    start_sec=hl.start_sec,
                    end_sec=hl.end_sec,
                    output_path=str(output_path),
                )
            except (FileNotFoundError, ValueError, VideoProbeError):
                # Skip this highlight on failure; keep processing the rest.
                continue

            clip = Clip(
                task_id=task_id,
                output_path=str(output_path),
                file_size=get_clip_file_size(str(output_path)),
                duration_sec=round(hl.end_sec - hl.start_sec, 2),
                resolution=resolution,
                highlight_ids=json.dumps([hl.id]),  # one highlight per clip (MVP)
            )
            db.add(clip)

        db.commit()

    finally:
        db.close()


# ============================================
# GET endpoints
# ============================================

@router.get("/", response_model=TaskListResponse)
def get_tasks(
    db: Session = Depends(get_db),
    status: Optional[str] = None,
    game_type: Optional[str] = None,
    skip: int = 0,
    limit: int = 20,
):
    """
    Return tasks with optional filtering and pagination.

    Query params (all optional):
        status: Filter by status ("pending" | "processing" | "done" | "failed")
        game_type: Filter by game type ("naraka", "lol", "overwatch", ...)
        skip: Number of records to skip (default 0)
        limit: Max records to return (default 20, capped at 100)

    Examples:
        GET /api/tasks                          -> first 20 tasks
        GET /api/tasks?limit=5                   -> first 5 tasks
        GET /api/tasks?skip=20&limit=20          -> tasks 21-40
        GET /api/tasks?status=done&limit=10      -> first 10 completed tasks
    """
    # Cap limit to prevent abuse
    if limit > 100:
        limit = 100
    if limit < 1:
        limit = 1
    if skip < 0:
        skip = 0

    # Build the filtered query
    query = db.query(Task)
    if status is not None:
        query = query.filter(Task.status == status)
    if game_type is not None:
        query = query.filter(Task.game_type == game_type)

    # Total count BEFORE pagination (for client to know total pages)
    total_count = query.count()

    # Apply pagination
    tasks = (
        query.order_by(Task.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )

    return {
        "tasks": tasks,
        "total": len(tasks),
        "total_count": total_count,
        "skip": skip,
        "limit": limit,
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
    """Trigger frame extraction in the background. Returns 202 Accepted."""
    task = db.query(Task).filter(Task.id == task_id).first()
    if task is None:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

    if task.status == "processing":
        raise HTTPException(
            status_code=409,
            detail=f"Task {task_id} is already being processed",
        )

    update_task_status(db, task, status="processing", progress=10)
    background_tasks.add_task(_run_frame_extraction_in_background, task_id, fps)

    return {
        "task_id": task_id,
        "status": "processing",
        "message": "Frame extraction started in background. Poll for status.",
        "fps": fps,
    }


@router.post("/{task_id}/generate-clips", status_code=202)
def generate_task_clips(
    task_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """
    Cut this task's high-score highlights (score >= MIN_CLIP_SCORE) into clip
    files, in the background. Returns 202 Accepted.

    Requires the task to have detected highlights already (run detection first).
    """
    task = db.query(Task).filter(Task.id == task_id).first()
    if task is None:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

    eligible = (
        db.query(Highlight)
        .filter(Highlight.task_id == task_id)
        .filter(Highlight.score >= MIN_CLIP_SCORE)
        .count()
    )
    if eligible == 0:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Task {task_id} has no highlights scoring >= {MIN_CLIP_SCORE}. "
                f"Run detection first, or lower the threshold."
            ),
        )

    background_tasks.add_task(_run_clip_generation_in_background, task_id)

    return {
        "task_id": task_id,
        "status": "generating_clips",
        "message": f"Cutting {eligible} clip(s) in background. Poll GET /{task_id}/clips.",
        "min_score": MIN_CLIP_SCORE,
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


@router.get("/{task_id}/clips")
def get_task_clips(task_id: int, db: Session = Depends(get_db)):
    """List generated clips for a task."""
    task = db.query(Task).filter(Task.id == task_id).first()
    if task is None:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

    clips = (
        db.query(Clip)
        .filter(Clip.task_id == task_id)
        .order_by(Clip.id)
        .all()
    )

    return {
        "task_id": task_id,
        "clip_count": len(clips),
        "clips": [
            {
                "id": c.id,
                "output_path": c.output_path,
                "file_size": c.file_size,
                "duration_sec": c.duration_sec,
                "resolution": c.resolution,
                "highlight_ids": json.loads(c.highlight_ids) if c.highlight_ids else [],
            }
            for c in clips
        ],
    }


@router.get("/{task_id}/progress")
def get_task_progress(task_id: int, db: Session = Depends(get_db)):
    """Real-time progress of frame extraction for a task."""
    task = db.query(Task).filter(Task.id == task_id).first()
    if task is None:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

    BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
    frames_dir = BACKEND_DIR / "frames" / str(task_id)

    if frames_dir.exists():
        current_frame_count = len(list(frames_dir.glob("frame_*.jpg")))
    else:
        current_frame_count = 0

    expected_total = 0
    if task.duration_sec:
        expected_total = int(task.duration_sec * 1)

    if task.status == "done":
        percent = 100
    elif task.status == "failed":
        percent = 0
    elif expected_total > 0:
        percent = int((current_frame_count / expected_total) * 100)
        percent = min(percent, 99)
    else:
        percent = 0

    if task.status == "pending":
        phase = "waiting"
    elif task.status == "processing":
        phase = "extracting_frames"
    elif task.status == "done":
        phase = "completed"
    elif task.status == "failed":
        phase = "failed"
    else:
        phase = "unknown"

    return {
        "task_id": task_id,
        "status": task.status,
        "progress": percent,
        "progress_detail": {
            "phase": phase,
            "current_frame": current_frame_count,
            "total_frames_expected": expected_total,
            "percent": percent,
        },
        "error_message": task.error_message,
    }