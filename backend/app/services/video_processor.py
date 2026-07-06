"""
Video processing service.

Wraps FFmpeg / ffprobe so the rest of the app doesn't deal with subprocess directly.

Functions:
- extract_video_metadata(): use ffprobe to read video metadata (duration, resolution, fps, etc.)
- extract_frames(): use ffmpeg to extract JPG frames at a given fps
"""

import json
import subprocess
from pathlib import Path


class VideoProbeError(Exception):
    """Raised when ffprobe / ffmpeg fails to process a video file."""
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


def extract_frames(
    video_path: str,
    output_dir: str,
    fps: int = 1,
) -> list[str]:
    """
    Extract frames from a video at a given rate using ffmpeg.

    Args:
        video_path: Path to source video file.
        output_dir: Directory to write JPG frames to (created if needed).
        fps: Frames per second to extract (default 1 = one frame per second).

    Returns:
        List of absolute paths to extracted JPG files, sorted by frame number.

    Raises:
        FileNotFoundError: video_path doesn't exist
        ValueError: fps out of range
        FileExistsError: output_dir already has frames in it (safety guard)
        VideoProbeError: ffmpeg fails
    """

    # 1. Validate inputs
    src = Path(video_path)
    if not src.exists():
        raise FileNotFoundError(f"Video file not found: {video_path}")

    if fps < 1 or fps > 60:
        raise ValueError(f"fps must be 1-60, got {fps}")

    # 2. Ensure output directory exists and is empty
    out_dir = Path(output_dir)
    if out_dir.exists() and any(out_dir.iterdir()):
        raise FileExistsError(
            f"Output directory not empty: {output_dir}. "
            f"Delete it first to re-extract."
        )
    out_dir.mkdir(parents=True, exist_ok=True)

    # 3. Build ffmpeg command
    # Pattern frame_%04d.jpg generates frame_0001.jpg, frame_0002.jpg, etc.
    output_pattern = str(out_dir / "frame_%04d.jpg")
    cmd = [
        "ffmpeg",
        "-i", str(src),
        "-vf", f"fps={fps}",
        "-q:v", "2",            # JPG quality (1=best, 31=worst), 2 = high quality
        "-loglevel", "error",   # suppress non-error log spam
        output_pattern,
    ]

    # 4. Run ffmpeg (this might take 30s-2min for a long video)
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600,  # 10 min max
        )
    except subprocess.TimeoutExpired:
        raise VideoProbeError(f"ffmpeg timed out extracting frames from {video_path}")

    if result.returncode != 0:
        raise VideoProbeError(f"ffmpeg failed: {result.stderr}")

    # 5. Collect generated file paths (sorted by frame number)
    frame_files = sorted(out_dir.glob("frame_*.jpg"))
    return [str(f) for f in frame_files]


def extract_thumbnail(
    video_path: str,
    time_sec: float,
    output_path: str,
    label: str = "",
    kill_count: int = 0,
) -> None:
    """
    Grab a still frame and render a stylized highlight cover.

    Pulls one frame at time_sec, then layers:
      - a light contrast/saturation lift (game capture often looks flat)
      - a vignette for a cinematic, focused look
      - a bottom gradient scrim for a poster feel
      - a gold accent bar on the left as a visual anchor
      - a big kill-type caption ("DOUBLE KILL") with gold outline + shadow
      - a smaller kill-count subtitle ("x2 KILLS")

    Uses fast input seeking (-ss before -i) for large source files.

    Args:
        video_path: Path to the source video.
        time_sec: Timestamp (seconds) of the frame to capture.
        output_path: Where to write the output image (e.g. .jpg).
        label: Highlight kind ("kill", "double_kill", ...). Drives the caption.
        kill_count: Number of kills in the streak (drives the subtitle).

    Raises:
        FileNotFoundError: source video missing.
        VideoProbeError: ffmpeg failed.
    """
    src = Path(video_path)
    if not src.exists():
        raise FileNotFoundError(f"Video file not found: {video_path}")

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    # Map the internal label to a display caption.
    caption_map = {
        "kill": "KILL",
        "double_kill": "DOUBLE KILL",
        "triple_kill": "TRIPLE KILL",
        "quadra_kill": "QUADRA KILL",
        "penta_kill": "PENTA KILL",
    }
    caption = caption_map.get(label, label.upper().replace("_", " "))

    font = "C\\:/Windows/Fonts/BebasNeue-Regular.ttf"
    # Streak heat colors, matching the montage captions.
    kind_color = {
        "kill": "white",
        "double_kill": "0xFFD24A",
        "triple_kill": "0xFF8C3B",
        "quadra_kill": "0xFF5252",
        "penta_kill": "0xFF2D2D",
    }
    accent = kind_color.get(label, "white")

    # Filter chain, applied in order.
    filters = [
        # 1. Subtle contrast + saturation lift (flat game capture -> punchier).
        "eq=contrast=1.08:saturation=1.15",
        # 2. Cinematic vignette (darkens the corners, focuses the center).
        "vignette=PI/5",
        # 3. Bottom scrim so captions stay readable over busy frames.
        "drawbox=x=0:y=ih*0.76:w=iw:h=ih*0.24:color=black@0.5:t=fill",
        # 4. Gold accent bar on the left, aligned with the caption.
        f"drawbox=x=iw*0.035:y=ih*0.79:w=iw*0.008:h=ih*0.13:color={accent}@0.95:t=fill",
    ]

    if caption:
        # 5. Main caption: big, white, gold outline + drop shadow.
        filters.append(
            "drawtext="
            f"fontfile='{font}':"
            f"text='{caption}':"
            f"fontcolor={accent}:"
            "fontsize=h/10:"
            "borderw=2:bordercolor=black@0.8:"
            "shadowcolor=black@0.7:shadowx=4:shadowy=4:"
            "x=w*0.055:"
            "y=h*0.77"
        )

    if kill_count and kill_count > 1:
        # 6. Subtitle with the kill count, under the main caption.
        filters.append(
            "drawtext="
            f"fontfile='{font}':"
            f"text='x{kill_count} KILLS':"
            "fontcolor=white@0.92:"
            "fontsize=h/26:"
            "borderw=3:bordercolor=black:"
            "x=w*0.055:"
            "y=h*0.90"
        )

    vf = ",".join(filters)

    cmd = [
        "ffmpeg",
        "-nostdin",
        "-ss", str(max(0.0, time_sec)),
        "-i", str(src),
        "-frames:v", "1",
        "-vf", vf,
        "-q:v", "2",
        "-loglevel", "error",
        "-y",
        str(out),
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except subprocess.TimeoutExpired:
        raise VideoProbeError(f"ffmpeg timed out grabbing thumbnail from {video_path}")

    if result.returncode != 0:
        raise VideoProbeError(f"ffmpeg failed grabbing thumbnail: {result.stderr}")
