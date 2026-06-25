"""
Clip assembler service.

Cuts highlight segments out of the source video using ffmpeg. Each highlight
(start_sec -> end_sec) becomes its own short mp4 clip. Clips can then be
concatenated into a montage and have background music mixed over them.

MVP scope: cut, concat, and BGM mixing. No transitions or subtitles yet.
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


def concat_clips(
    clip_paths: list[str],
    output_path: str,
) -> list[float]:
    """
    Concatenate multiple clips into a single video, in order.

    All clips are assumed to share the same codec / resolution / parameters
    (they are produced by the same cut_clip call), so the concat demuxer can
    join them with stream copy (no re-encode) for a fast, lossless stitch.

    Args:
        clip_paths: Ordered list of clip file paths to join.
        output_path: Where to write the concatenated video.

    Raises:
        ValueError: empty clip list.
        FileNotFoundError: a clip path is missing.
        VideoProbeError: ffmpeg failed.
    """
    if not clip_paths:
        raise ValueError("concat_clips: clip_paths is empty")

    for p in clip_paths:
        if not Path(p).exists():
            raise FileNotFoundError(f"Clip not found: {p}")

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    # The concat demuxer reads a text file listing the inputs. Each line is:
    #   file 'absolute/path/to/clip.mp4'
    # Single quotes inside a path must be escaped as '\'' for ffmpeg.
    list_file = out.parent / "_concat_list.txt"
    with open(list_file, "w", encoding="utf-8") as f:
        for p in clip_paths:
            safe = str(Path(p).resolve()).replace("'", "'\\''")
            f.write(f"file '{safe}'\n")

    cmd = [
        "ffmpeg",
        "-nostdin",
        "-f", "concat",
        "-safe", "0",           # allow absolute paths in the list file
        "-i", str(list_file),
        "-c", "copy",           # stream copy: no re-encode, fast and lossless
        "-loglevel", "error",
        "-y",
        str(out),
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,
        )
    finally:
        # Clean up the temporary list file regardless of success.
        if list_file.exists():
            list_file.unlink()

    if result.returncode != 0:
        raise VideoProbeError(f"ffmpeg failed concatenating clips: {result.stderr}")

    # Measure each clip's real duration with ffprobe so callers can build an
    # accurate timeline (clip durations can drift slightly from the DB value
    # due to re-encoding). Returned in the same order as clip_paths.
    durations: list[float] = []
    for p in clip_paths:
        probe = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(p),
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        try:
            durations.append(float(probe.stdout.strip()))
        except (ValueError, AttributeError):
            durations.append(0.0)
    return durations


def add_bgm(
    video_path: str,
    bgm_path: str,
    output_path: str,
    original_volume: float = 0.25,
    bgm_volume: float = 1.0,
    captions: list[dict] | None = None,
) -> None:
    """
    Mix BGM over a video and optionally burn in timed kill captions.

    BGM is the main track; original game audio is ducked. If captions are
    given, each one is drawn (top-center, Impact, gold outline) only during
    its time window, so each highlight in the montage gets its own pop-up
    caption like "DOUBLE KILL".

    Args:
        video_path: Path to the concatenated video with its original audio.
        bgm_path: Path to the BGM audio file.
        output_path: Where to write the final mixed video.
        original_volume: Multiplier for the original game audio (0.0-1.0).
        bgm_volume: Multiplier for the BGM track.
        captions: Optional list of dicts, each:
            {"start": float, "text": str, "duration": float}
            text is shown from start to start+duration seconds.

    Raises:
        FileNotFoundError: video or bgm missing.
        VideoProbeError: ffmpeg failed.
    """
    src = Path(video_path)
    if not src.exists():
        raise FileNotFoundError(f"Video not found: {video_path}")
    bgm = Path(bgm_path)
    if not bgm.exists():
        raise FileNotFoundError(f"BGM not found: {bgm_path}")

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    # -stream_loop -1 loops the BGM so short tracks still cover the whole video.
    # audio_filter:
    #   [0:a] original audio, scaled down by original_volume
    #   [1:a] looped BGM, scaled by bgm_volume
    #   amix mixes both; duration=first ties output length to the video.
    #   dropout_transition=0 keeps BGM at full level even if original is silent.
    audio_filter = (
        f"[0:a]volume={original_volume}[a0];"
        f"[1:a]volume={bgm_volume}[a1];"
        f"[a0][a1]amix=inputs=2:duration=first:dropout_transition=0[aout]"
    )

    cmd = [
        "ffmpeg",
        "-nostdin",
        "-i", str(src),
        "-stream_loop", "-1",
        "-i", str(bgm),
    ]

    if captions:
        # Build a video filter chain: one timed drawtext per caption.
        font = "C\\:/Windows/Fonts/impact.ttf"
        gold = "0xFFD24A"
        draw_parts = []
        for c in captions:
            start = float(c["start"])
            end = start + float(c.get("duration", 2.5))
            text = str(c["text"])
            draw_parts.append(
                "drawtext="
                f"fontfile='{font}':"
                f"text='{text}':"
                "fontcolor=white:"
                "fontsize=h/11:"
                f"borderw=5:bordercolor={gold}:"
                "shadowcolor=black@0.7:shadowx=4:shadowy=4:"
                "x=(w-text_w)/2:"
                "y=h*0.08:"
                f"enable='between(t,{start:.3f},{end:.3f})'"
            )
        video_filter = "[0:v]" + ",".join(draw_parts) + "[vout]"
        full_filter = f"{audio_filter};{video_filter}"
        cmd += [
            "-filter_complex", full_filter,
            "-map", "[vout]",
            "-map", "[aout]",
            "-c:v", "libx264",
            "-preset", "veryfast",
        ]
    else:
        cmd += [
            "-filter_complex", audio_filter,
            "-map", "0:v",
            "-map", "[aout]",
            "-c:v", "copy",
        ]

    cmd += [
        "-c:a", "aac",
        "-shortest",
        "-loglevel", "error",
        "-y",
        str(out),
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,
        )
    except subprocess.TimeoutExpired:
        raise VideoProbeError(f"ffmpeg timed out adding BGM to {video_path}")

    if result.returncode != 0:
        raise VideoProbeError(f"ffmpeg failed adding BGM: {result.stderr}")