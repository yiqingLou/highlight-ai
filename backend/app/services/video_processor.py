"""
Video processing service.

Wraps FFmpeg / ffprobe so the rest of the app doesn't deal with subprocess directly.
"""

import json
import subprocess
from pathlib import Path
from typing import Optional


class VideoProbeError(Exception):
    """Raised when ffprobe fails to read a video file."""
    pass


def extract_video_metadata(file_path: str) -> dict:
    """
    Extract metadata from a video file using ffprobe.

    Args:
        file_path: Absolute path to the video file.

    Returns:
        Dict with keys:
            duration_sec: float (e.g. 3600.0)
            width: int (e.g. 1920)
            height: int (e.g. 1080)
            fps: float (e.g. 60.0)
            file_size: int (bytes)
            video_codec: str (e.g. "h264")
            audio_codec: str or None

    Raises:
        FileNotFoundError: if file_path doesn't exist
        VideoProbeError: if ffprobe fails or returns no video stream
    """

    # 1. Check file exists first (clearer error than ffprobe's)
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Video file not found: {file_path}")

    # 2. Build ffprobe command
    cmd = [
        "ffprobe",
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        str(path),
    ]

    # 3. Run ffprobe, capture output
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except subprocess.TimeoutExpired:
        raise VideoProbeError(f"ffprobe timed out on {file_path}")
    except FileNotFoundError:
        raise VideoProbeError("ffprobe command not found - is FFmpeg installed?")

    if result.returncode != 0:
        raise VideoProbeError(f"ffprobe failed: {result.stderr}")

    # 4. Parse JSON
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        raise VideoProbeError(f"ffprobe returned invalid JSON: {e}")

    # 5. Find the video stream (might not be stream[0])
    video_stream = None
    audio_stream = None
    for s in data.get("streams", []):
        if s.get("codec_type") == "video" and video_stream is None:
            video_stream = s
        elif s.get("codec_type") == "audio" and audio_stream is None:
            audio_stream = s

    if video_stream is None:
        raise VideoProbeError(f"No video stream found in {file_path}")

    # 6. Parse fps (it's a fraction string like "30/1" or "60000/1001")
    fps_str = video_stream.get("r_frame_rate", "0/1")
    try:
        num, denom = fps_str.split("/")
        fps = float(num) / float(denom) if float(denom) != 0 else 0.0
    except (ValueError, ZeroDivisionError):
        fps = 0.0

    # 7. Build result
    format_info = data.get("format", {})

    return {
        "duration_sec": float(format_info.get("duration", 0)),
        "width": int(video_stream.get("width", 0)),
        "height": int(video_stream.get("height", 0)),
        "fps": round(fps, 3),
        "file_size": int(format_info.get("size", 0)),
        "video_codec": video_stream.get("codec_name"),
        "audio_codec": audio_stream.get("codec_name") if audio_stream else None,
    }