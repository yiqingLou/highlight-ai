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
  POST /{id}/montage                  - Stitch clips into one montage + optional BGM (background, 202)
"""

import ast
import json
import shutil
import time
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.database import SessionLocal, get_db
from app.models import Task, Highlight, Clip
from app.schemas.task import TaskListResponse, TaskDetailResponse, TaskCreate
from app.services.video_processor import (
    extract_video_metadata,
    extract_frames,
    extract_thumbnail,
    VideoProbeError,
)
from app.services.clip_assembler import (
    cut_clip,
    get_clip_file_size,
    apply_kill_slowmo,
    _probe_duration,
    concat_clips,
    concat_clips_with_transitions,
    make_title_card,
    add_bgm,
)
from app.services.viral_score import compute_viral_score_from_meta
from app.game_profiles.base import get_profile

router = APIRouter()

# ViralScore threshold for entering the montage. Single kills score ~56,
# double kills ~66-74, so 60 keeps strong multi-kills and lets a long single
# squeak in, while filtering the weakest. Tune after seeing real distributions.
MIN_CLIP_SCORE = 60

# Montage keeps the top-N highlights by ViralScore. Multi-kills score highest
# so they fill the slots first; strong single kills backfill when there are
# fewer multi-kills than N. Keeps the reel tight instead of dumping everything.
MONTAGE_TOP_N = 6

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

            # ViralScore: fuse streak level + real kill span into a 0-100
            # excitement score (replaces the flat kind lookup table).
            score_100 = compute_viral_score_from_meta(dh.kind, dh.meta)

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


def _run_clip_generation_in_background(task_id: int, slowmo: bool = True) -> None:
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

        # --- Step 1: load the top-N highlights by ViralScore, best first ---
        # No score gate: ranking by ViralScore + a top-N cap naturally keeps
        # the most exciting clips (multi-kills first, strong singles backfill).
        highlights = (
            db.query(Highlight)
            .filter(Highlight.task_id == task_id)
            .order_by(Highlight.score.desc())
            .limit(MONTAGE_TOP_N)
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

            # --- Optional: speed-ramp slow-mo leading into the kill ---
            # Singles only for now (multi-kill windows are more complex).
            if slowmo and hl.label == "kill":
                try:
                    meta = ast.literal_eval(hl.reason) if hl.reason else {}
                    first_kill = float(meta.get("first_kill_sec", 0.0))
                    kill_in_clip = first_kill - hl.start_sec
                    # Ramp needs ~1.8s of runway before the kill.
                    if kill_in_clip > 1.8:
                        tmp_path = clips_dir / f"_slowmo_{idx:03d}.mp4"
                        apply_kill_slowmo(
                            str(output_path), str(tmp_path),
                            kill_sec=kill_in_clip,
                        )
                        tmp_path.replace(output_path)
                except (ValueError, VideoProbeError, OSError):
                    # Slow-mo is best-effort; keep the plain clip on failure.
                    pass

            clip = Clip(
                task_id=task_id,
                output_path=str(output_path),
                file_size=get_clip_file_size(str(output_path)),
                duration_sec=round(_probe_duration(str(output_path)), 2),
                resolution=resolution,
                highlight_ids=json.dumps([hl.id]),  # one highlight per clip (MVP)
            )
            db.add(clip)
            # Real per-clip progress for the frontend poll.
            update_task_status(
                db, task, status="processing",
                progress=int((idx + 1) / len(highlights) * 100),
            )

        db.commit()
        update_task_status(db, task, status="done", progress=100)

    finally:
        db.close()


def _run_montage_in_background(
    task_id: int,
    bgm_path: Optional[str],
    captions_enabled: bool = True,
    transitions: bool = True,
    intro_outro: bool = True,
    player_name: str = "",
    clip_ids: str = "",
) -> None:
    """
    Background worker: stitch a task's clips into one montage, mix BGM, and
    burn in timed kill captions.

    Pipeline:
        1. Collect this task's clip files in order
        2. Concatenate them; concat_clips returns each clip's real duration
        3. Build a caption timeline: for each clip, look up its highlight's
           label and place a "DOUBLE KILL"-style caption at the clip's start
           offset in the montage
        4. Mix BGM and burn the captions in one pass; if no BGM, keep the
           concatenated video as the result
        5. Leave the final file at clips/{task_id}/montage_final.mp4

    Errors are written to the task's error_message; the montage is best-effort.
    """
    db = SessionLocal()
    try:
        task = db.query(Task).filter(Task.id == task_id).first()
        if task is None:
            return

        BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
        clips_dir = BACKEND_DIR / "clips" / str(task_id)

        # --- Step 1: collect clip files in name order ---
        clip_files = sorted(clips_dir.glob("clip_*.mp4"))
        # Optional user selection: keep only the chosen clips (Clip DB ids).
        if clip_ids:
            try:
                wanted = {int(x) for x in clip_ids.split(",") if x.strip()}
            except ValueError:
                wanted = set()
            if wanted:
                rows = db.query(Clip).filter(Clip.id.in_(wanted)).all()
                keep = {Path(r.output_path).name for r in rows}
                clip_files = [p for p in clip_files if p.name in keep]
        if not clip_files:
            update_task_status(
                db, task, status=task.status,
                error_message="No clips to assemble. Run generate-clips first.",
            )
            return

        clip_paths = [str(p) for p in clip_files]
        raw_montage = clips_dir / "_montage_raw.mp4"
        final_montage = clips_dir / "montage_final.mp4"

        # --- Optional: build intro + outro title cards ---
        INTRO_SEC = 3.0
        OUTRO_SEC = 3.0
        intro_path = None
        outro_path = None
        update_task_status(db, task, status="processing", progress=10)
        if intro_outro:
            # Intro background: a clean gameplay frame from the first kill.
            first_kill_bg = None
            try:
                first_clip_row = (
                    db.query(Clip)
                    .filter(Clip.output_path == clip_paths[0])
                    .first()
                )
                # Fall back to no background (solid black) if we can't find a frame.
            except Exception:
                pass
            intro_path = str(clips_dir / "_intro.mp4")
            make_title_card(
                "NARAKA HIGHLIGHTS", intro_path,
                bg_image=first_kill_bg, duration=INTRO_SEC,
            )
            outro_path = str(clips_dir / "_outro.mp4")
            make_title_card(
                player_name.strip() or "HIGHLIGHT AI", outro_path,
                bg_image=None, duration=OUTRO_SEC,
            )

        # --- Step 2: concatenate clips (returns each clip's real duration) ---
        TRANSITION_SEC = 1.1
        assembly_paths = list(clip_paths)
        if intro_outro:
            assembly_paths = [intro_path] + assembly_paths + [outro_path]

        # Transition plan: flash-white entering a multi-kill segment,
        # plain crossfade everywhere else - the flash cues the hype.
        MULTI_KILL_FLASH = "fadewhite"
        seg_labels = []
        if intro_outro:
            seg_labels.append(None)  # intro card
        for cf in clip_files:
            row = db.query(Clip).filter(Clip.output_path == str(cf)).first()
            lbl = None
            if row and row.highlight_ids:
                try:
                    ids = json.loads(row.highlight_ids)
                    h = db.query(Highlight).filter(Highlight.id == ids[0]).first()
                    lbl = h.label if h else None
                except (ValueError, TypeError):
                    pass
            seg_labels.append(lbl)
        if intro_outro:
            seg_labels.append(None)  # outro card
        transition_types = []
        for i in range(1, len(seg_labels)):
            if seg_labels[i] in (
                "double_kill", "triple_kill", "quadra_kill", "penta_kill"
            ):
                transition_types.append(MULTI_KILL_FLASH)
            else:
                transition_types.append("fade")

        def _gap_dur(g: int) -> float:
            t = transition_types[g] if g < len(transition_types) else "fade"
            return 0.4 if t in ("fadewhite", "fadeblack") else TRANSITION_SEC

        try:
            if transitions:
                durations = concat_clips_with_transitions(
                    assembly_paths, str(raw_montage),
                    transition_duration=TRANSITION_SEC,
                    transition_types=transition_types,
                )
            else:
                durations = concat_clips(assembly_paths, str(raw_montage))
        except (ValueError, FileNotFoundError, VideoProbeError) as e:
            update_task_status(
                db, task, status=task.status,
                error_message=f"Montage concat failed: {e}",
            )
            return

        update_task_status(db, task, status="processing", progress=50)

        # --- Step 3: build the caption timeline ---
        caption_map = {
            "kill": "KILL",
            "double_kill": "DOUBLE KILL",
            "triple_kill": "TRIPLE KILL",
            "quadra_kill": "QUADRA KILL",
            "penta_kill": "PENTA KILL",
        }
        captions = []
        # Cursor starts after the intro card (if any).
        cursor = durations[0] if intro_outro else 0.0
        # durations for the actual clips (skip intro/outro entries)
        clip_durations = durations[1:-1] if intro_outro else durations

        clean_bgm = bgm_path if (bgm_path and Path(bgm_path).exists()) else None

        # --- Beat sync: land a strong BGM beat on the first kill ---
        bgm_offset = 0.0
        if clean_bgm and clip_files:
            try:
                from app.services.beat_sync import (
                    detect_hits,
                    bgm_trim_for_kill,
                )

                first_clip_row = None
                first_clip_hl = None
                for clip_file, _ in zip(clip_files, clip_durations):
                    clip_row = (
                        db.query(Clip)
                        .filter(Clip.output_path == str(clip_file))
                        .first()
                    )
                    if clip_row and clip_row.highlight_ids:
                        try:
                            hl_ids = json.loads(clip_row.highlight_ids)
                            if hl_ids:
                                first_clip_hl = db.query(Highlight).filter(
                                    Highlight.id == hl_ids[0]
                                ).first()
                                if first_clip_hl:
                                    first_clip_row = clip_row
                                    break
                        except (ValueError, TypeError):
                            pass

                if first_clip_hl:
                    meta = ast.literal_eval(first_clip_hl.reason)
                    kill_orig = float(meta["first_kill_sec"]) - first_clip_hl.start_sec
                    orig_dur = first_clip_hl.end_sec - first_clip_hl.start_sec
                    delta = clip_durations[0] - orig_dur
                    kill_in_clip = kill_orig + max(0.0, delta)
                    t_kill = (durations[0] if intro_outro else 0.0) \
                        - (_gap_dur(0) if transitions else 0.0) + kill_in_clip
                    BEAT_SYNC_CALIB = 0.4  # manual fine-tune: positive = hit lands earlier
                    beats = detect_hits(clean_bgm)
                    bgm_offset = bgm_trim_for_kill(t_kill, beats) + BEAT_SYNC_CALIB
            except Exception:
                bgm_offset = 0.0

        for gi, (clip_file, dur) in enumerate(zip(clip_files, clip_durations)):
            clip_row = (
                db.query(Clip)
                .filter(Clip.output_path == str(clip_file))
                .first()
            )
            label = None
            if clip_row and clip_row.highlight_ids:
                try:
                    hl_ids = json.loads(clip_row.highlight_ids)
                    if hl_ids:
                        hl = db.query(Highlight).filter(
                            Highlight.id == hl_ids[0]
                        ).first()
                        if hl:
                            label = hl.label
                except (ValueError, TypeError):
                    pass

            if label:
                text = caption_map.get(label, label.upper().replace("_", " "))
                captions.append({
                    "start": round(cursor, 3),
                    "text": text,
                    "duration": 2.5,
                    "kind": label,
                })
            cursor += dur
            if transitions:
                cursor -= _gap_dur(gi + 1 if intro_outro else gi)

        # --- Step 4: finalize — optionally mix BGM, optionally burn captions ---
        # add_bgm handles all four combinations; bgm_path=None just skips BGM
        # while still burning captions, so captions no longer depend on BGM.
        update_task_status(db, task, status="processing", progress=75)
        try:
            add_bgm(
                str(raw_montage), str(final_montage),
                bgm_path=clean_bgm,
                captions=captions if (captions and captions_enabled) else None,
                bgm_offset_sec=bgm_offset,
            )
        except (FileNotFoundError, VideoProbeError) as e:
            update_task_status(
                db, task, status=task.status,
                error_message=f"Montage finalize failed: {e}",
            )
            return

        update_task_status(db, task, status="done", progress=100)

    finally:
        db.close()


def _kill_time_for_highlight(hl) -> float:
    """
    Best timestamp (seconds) to grab a cover frame for a highlight.

    Prefer the first kill time stored in the highlight's reason meta (that
    frame is guaranteed to contain the kill scratch, since YOLO detected it
    there). Fall back to the midpoint of the clip if meta is unavailable.
    """
    # reason is a Python dict repr like "{'source': 'yolo', 'first_kill_sec': 190.0, ...}"
    # Offset added to the kill time. Frames are sampled at 1 fps, so the
    # frame-index-to-seconds conversion can be up to ~1s early relative to
    # the real video timestamp. Nudging forward lands more reliably inside
    # the scratch icon's on-screen window.
    SCRATCH_OFFSET_SEC = 0.5

    if hl.reason:
        try:
            meta = ast.literal_eval(hl.reason)
            if isinstance(meta, dict) and "first_kill_sec" in meta:
                return float(meta["first_kill_sec"]) + SCRATCH_OFFSET_SEC
        except (ValueError, SyntaxError):
            pass
    # Fallback: midpoint of the clip.
    return (hl.start_sec + hl.end_sec) / 2

def _run_thumbnail_generation_in_background(task_id: int) -> None:
    """
    Background worker: grab a cover frame for each highlight of a task.

    For every highlight, capture a still at its first kill moment (the frame
    that actually shows the kill scratch) and store it under
    thumbnails/{task_id}/, then save the path on the highlight row.

    Best-effort: a failure on one highlight is skipped, not fatal.
    """
    db = SessionLocal()
    try:
        task = db.query(Task).filter(Task.id == task_id).first()
        if task is None:
            return

        BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
        thumbs_dir = BACKEND_DIR / "thumbnails" / str(task_id)
        thumbs_dir.mkdir(parents=True, exist_ok=True)

        highlights = (
            db.query(Highlight)
            .filter(Highlight.task_id == task_id)
            .order_by(Highlight.sort_order)
            .all()
        )

        for hl in highlights:
            time_sec = _kill_time_for_highlight(hl)
            output_path = thumbs_dir / f"hl_{hl.id:04d}.jpg"

            # Pull kill_count from the reason meta for the subtitle.
            kill_count = 0
            if hl.reason:
                try:
                    meta = ast.literal_eval(hl.reason)
                    if isinstance(meta, dict):
                        kill_count = int(meta.get("kill_count", 0))
                except (ValueError, SyntaxError):
                    pass

            try:
                extract_thumbnail(
                    video_path=task.file_path,
                    time_sec=time_sec,
                    output_path=str(output_path),
                    label=hl.label,
                    kill_count=kill_count,
                )
            except (FileNotFoundError, VideoProbeError):
                # Skip this highlight on failure; keep going.
                continue

            hl.thumbnail_path = str(output_path)

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


@router.delete("/{task_id}", status_code=204)
def delete_task(task_id: int, db: Session = Depends(get_db)):
    """Delete a task, its DB rows, and its on-disk artifacts.

    The source video is removed ONLY if it lives in our uploads/ folder
    (app-owned copy). Videos referenced by local path are never touched.
    """
    task = db.query(Task).filter(Task.id == task_id).first()
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")

    BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
    for d in (
        BACKEND_DIR / "frames" / str(task_id),
        BACKEND_DIR / "clips" / str(task_id),
        BACKEND_DIR / "thumbnails" / str(task_id),
    ):
        shutil.rmtree(d, ignore_errors=True)

    uploads_dir = BACKEND_DIR / "uploads"
    fp = Path(task.file_path)
    try:
        if fp.exists() and uploads_dir in fp.parents:
            fp.unlink()
    except OSError:
        pass  # best-effort: a locked file shouldn't block the delete

    db.query(Highlight).filter(Highlight.task_id == task_id).delete()
    db.query(Clip).filter(Clip.task_id == task_id).delete()
    db.delete(task)
    db.commit()


# ============================================
# POST endpoints
# ============================================

@router.post("/upload", status_code=201)
async def upload_task_video(file: UploadFile, db: Session = Depends(get_db)):
    """Accept a video upload, store it under backend/uploads/, create a task.

    The file is streamed to disk in chunks so multi-GB uploads never sit in
    memory. If a task already exists for the stored path, that task is
    returned instead of a duplicate.
    """
    if not file.filename or not file.filename.lower().endswith(".mp4"):
        raise HTTPException(status_code=400, detail="Only .mp4 files are supported")

    BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
    uploads_dir = BACKEND_DIR / "uploads"
    uploads_dir.mkdir(parents=True, exist_ok=True)

    # Avoid collisions: prefix with a timestamp if the name is taken.
    dest = uploads_dir / file.filename
    if dest.exists():
        stem, suffix = dest.stem, dest.suffix
        dest = uploads_dir / f"{stem}_{int(time.time())}{suffix}"

    CHUNK = 8 * 1024 * 1024  # 8 MB
    try:
        with open(dest, "wb") as out:
            while True:
                chunk = await file.read(CHUNK)
                if not chunk:
                    break
                out.write(chunk)
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"Failed to store upload: {e}")

    file_path = str(dest).replace("\\", "/")
    existing = db.query(Task).filter(Task.file_path == file_path).first()
    if existing:
        return existing

    try:
        metadata = extract_video_metadata(file_path)
    except (FileNotFoundError, VideoProbeError) as e:
        # Stored but not a readable video — remove it and reject.
        dest.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=f"Cannot read video: {e}")

    task = Task(
        file_path=file_path,
        file_name=dest.name,
        file_size=metadata["file_size"],
        duration_sec=metadata["duration_sec"],
        width=metadata["width"],
        height=metadata["height"],
        fps=metadata["fps"],
        game_type="naraka",
        status="pending",
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task

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
    slowmo: bool = True,
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
        .count()
    )
    if eligible == 0:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Task {task_id} has no highlights detected yet. "
                f"Run detection first."
            ),
        )

    if task.status == "processing":
        raise HTTPException(
            status_code=409,
            detail="Task is already processing; wait for the current stage to finish",
        )

    update_task_status(db, task, status="processing", progress=0)
    background_tasks.add_task(_run_clip_generation_in_background, task_id, slowmo)

    return {
        "task_id": task_id,
        "status": "generating_clips",
        "message": f"Cutting top {MONTAGE_TOP_N} highlights in background. Poll GET /{task_id}/clips.",
    }


@router.post("/{task_id}/montage", status_code=202)
def generate_task_montage(
    task_id: int,
    background_tasks: BackgroundTasks,
    bgm: Optional[str] = None,
    captions: bool = True,
    transitions: bool = True,
    intro_outro: bool = True,
    player_name: str = "",
    clip_ids: str = "",
    db: Session = Depends(get_db),
):
    """
    Stitch this task's clips into a single montage, optionally with BGM mixed
    over it. Returns 202 Accepted; runs in the background.

    Query params:
        bgm: Optional path to a BGM audio file. If omitted, the montage has
             only the original (concatenated) game audio.

    Requires clips to exist already (run generate-clips first).
    Output: clips/{task_id}/montage_final.mp4
    """
    task = db.query(Task).filter(Task.id == task_id).first()
    if task is None:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

    BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
    clips_dir = BACKEND_DIR / "clips" / str(task_id)
    clip_count = len(list(clips_dir.glob("clip_*.mp4"))) if clips_dir.exists() else 0
    if clip_count == 0:
        raise HTTPException(
            status_code=409,
            detail=f"Task {task_id} has no clips. Run generate-clips first.",
        )

    # Strip stray whitespace from the path (e.g. an accidental leading space
    # in the query param), so Path.exists() does not silently miss the file.
    bgm_clean = bgm.strip() if bgm else None
    if task.status == "processing":
        raise HTTPException(
            status_code=409,
            detail="Task is already processing; wait for the current stage to finish",
        )
    update_task_status(db, task, status="processing", progress=0)
    background_tasks.add_task(
        _run_montage_in_background, task_id, bgm_clean, captions, transitions, intro_outro, player_name, clip_ids
    )

    return {
        "task_id": task_id,
        "status": "assembling_montage",
        "message": f"Assembling {clip_count} clips into a montage in background.",
        "bgm": bgm,
        "output": f"clips/{task_id}/montage_final.mp4",
    }


@router.post("/{task_id}/thumbnails", status_code=202)
def generate_task_thumbnails(
    task_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """
    Grab a cover frame for each highlight (at its kill moment) in the
    background. Returns 202 Accepted.

    Requires highlights to exist already (run detection first).
    Output: thumbnails/{task_id}/hl_{id}.jpg, path saved on each highlight.
    """
    task = db.query(Task).filter(Task.id == task_id).first()
    if task is None:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

    count = db.query(Highlight).filter(Highlight.task_id == task_id).count()
    if count == 0:
        raise HTTPException(
            status_code=409,
            detail=f"Task {task_id} has no highlights. Run detection first.",
        )

    background_tasks.add_task(_run_thumbnail_generation_in_background, task_id)

    return {
        "task_id": task_id,
        "status": "generating_thumbnails",
        "message": f"Grabbing cover frames for {count} highlight(s) in background.",
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
        "progress": 100 if task.status == "done" else (task.progress or 0),
        "progress_detail": {
            "phase": phase,
            "current_frame": current_frame_count,
            "total_frames_expected": expected_total,
            "percent": percent,
        },
        "error_message": task.error_message,
    }