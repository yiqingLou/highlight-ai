"""
Clip assembler service.

Cuts highlight segments out of the source video using ffmpeg. Each highlight
(start_sec -> end_sec) becomes its own short mp4 clip.

MVP scope: one clip per highlight, accurate re-encode cut. No concatenation,
BGM, or subtitles yet (those come later).
"""

import subprocess
from pathlib import Path

from app.services.video_processor import VideoProbeError


def cut_clip(
    video_path: str,
    start_sec: float,
    end_sec: float,
    output_path: str,
) -> None:
    """
    Cut a single segment [start_sec, end_sec] from a video using ffmpeg.

    Uses fast input seeking (-ss before -i) so ffmpeg jumps straight to the
    start time instead of decoding the whole file up to that point. This is
    essential for large source files (multi-GB); decoding from frame 0 every
    time would time out. Modern ffmpeg keeps this frame-accurate when
    re-encoding.

    Args:
        video_path: Path to the source video.
        start_sec: Segment start time in seconds.
        end_sec: Segment end time in seconds.
        output_path: Where to write the output mp4.

    Raises:
        FileNotFoundError: source video missing.
        ValueError: invalid time range.
        VideoProbeError: ffmpeg failed.
    """
    src = Path(video_path)
    if not src.exists():
        raise FileNotFoundError(f"Video file not found: {video_path}")

    if end_sec <= start_sec:
        raise ValueError(f"end_sec ({end_sec}) must be > start_sec ({start_sec})")

    duration = end_sec - start_sec

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    # Fast seek: -ss BEFORE -i jumps directly to the start time without
    # decoding everything before it. -t (duration) stays after -i so it counts
    # from the sought position.
    cmd = [
        "ffmpeg",
        "-ss", str(start_sec),   # fast input seek (before -i)
        "-i", str(src),
        "-t", str(duration),
        "-c:v", "libx264",
        "-c:a", "aac",
        "-preset", "veryfast",   # quicker encode for 2560x1600 clips
        "-loglevel", "error",
        "-y",                    # overwrite if exists
        str(out),
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,  # 5 min max per clip (clips are short)
        )
    except subprocess.TimeoutExpired:
        raise VideoProbeError(f"ffmpeg timed out cutting clip from {video_path}")

    if result.returncode != 0:
        raise VideoProbeError(f"ffmpeg failed cutting clip: {result.stderr}")


def get_clip_file_size(output_path: str) -> int:
    """Return the size in bytes of a generated clip file (0 if missing)."""
    p = Path(output_path)
    return p.stat().st_size if p.exists() else 0