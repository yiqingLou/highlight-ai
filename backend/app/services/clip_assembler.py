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
    output_path: str,
    bgm_path: str | None = None,
    original_volume: float = 0.45,
    bgm_volume: float = 0.8,
    captions: list[dict] | None = None,
) -> None:
    """
    Finalize a montage: optionally mix BGM and optionally burn in kill captions.

    Both BGM and captions are independent and optional, so all four
    combinations work in a single ffmpeg pass (one re-encode at most):
      - bgm + captions: ducked game audio under looped BGM, captions on top
      - bgm only:       ducked game audio under looped BGM
      - captions only:  original audio untouched, captions burned in
      - neither:        a plain copy (no re-encode)

    Args:
        video_path: The concatenated montage video (with original audio).
        output_path: Where to write the final video.
        bgm_path: Optional BGM audio file. If None, original audio is kept.
        original_volume: Multiplier for original game audio when mixing BGM.
        bgm_volume: Multiplier for the BGM track.
        captions: Optional list of {"start": float, "text": str,
                  "duration": float}; each is shown during its time window.

    Raises:
        FileNotFoundError: video (or given bgm) missing.
        VideoProbeError: ffmpeg failed.
    """
    src = Path(video_path)
    if not src.exists():
        raise FileNotFoundError(f"Video not found: {video_path}")

    use_bgm = bgm_path is not None and Path(bgm_path).exists()
    use_captions = bool(captions)

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    # Fast path: nothing to do but copy.
    if not use_bgm and not use_captions:
        cmd = [
            "ffmpeg", "-nostdin",
            "-i", str(src),
            "-c", "copy",
            "-loglevel", "error",
            "-y",
            str(out),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if result.returncode != 0:
            raise VideoProbeError(f"ffmpeg failed copying montage: {result.stderr}")
        return

    cmd = ["ffmpeg", "-nostdin", "-i", str(src)]
    if use_bgm:
        cmd += ["-stream_loop", "-1", "-i", str(bgm_path)]

    filter_parts = []

    # --- Video: burn captions if any ---
    if use_captions:
        font = "C\\:/Windows/Fonts/BebasNeue-Regular.ttf"
        # Streak heat colors: singles stay clean white, multi-kills warm up.
        kind_color = {
            "kill": "white",
            "double_kill": "0xFFD24A",   # gold
            "triple_kill": "0xFF8C3B",   # orange
            "quadra_kill": "0xFF5252",   # red-orange
            "penta_kill": "0xFF2D2D",    # red
        }
        draw_parts = []
        for c in captions:
            start = float(c["start"])
            end = start + float(c.get("duration", 2.5))
            text = str(c["text"])
            # Fade in over 0.3s after start, fade out over 0.3s before end.
            fade = (
                f"if(lt(t,{start:.3f}+0.3),(t-{start:.3f})/0.3,"
                f"if(gt(t,{end:.3f}-0.3),({end:.3f}-t)/0.3,1))"
            )
            # Accent bar: a thin vertical white line left of the text,
            # lower-left placement (doesn't cover the crosshair).
            draw_parts.append(
                "drawbox="
                "x=iw*0.045:"
                "y=ih*0.705:"
                "w=iw*0.0025:"
                "h=ih*0.06:"
                f"color={kind_color.get(c.get('kind', 'kill'), 'white')}@0.9:t=fill:"
                f"enable='between(t,{start:.3f},{end:.3f})'"
            )
            # Clean white text with a soft shadow, fading in/out.
            draw_parts.append(
                "drawtext="
                f"fontfile='{font}':"
                f"text='{text}':"
                f"fontcolor={kind_color.get(c.get('kind', 'kill'), 'white')}:"
                "fontsize=h/12:"
                "shadowcolor=black@0.8:shadowx=3:shadowy=3:"
                f"alpha='{fade}':"
                "x=w*0.055:"
                "y=h*0.71:"
                f"enable='between(t,{start:.3f},{end:.3f})'"
            )
        filter_parts.append("[0:v]" + ",".join(draw_parts) + "[vout]")

    # --- Audio: mix BGM if any ---
    if use_bgm:
        filter_parts.append(
            f"[0:a]volume={original_volume}[a0];"
            f"[1:a]volume={bgm_volume}[a1];"
            f"[a0][a1]amix=inputs=2:duration=first:dropout_transition=0[aout]"
        )

    cmd += ["-filter_complex", ";".join(filter_parts)]

    # Map video: captioned stream if burned, else original.
    cmd += ["-map", "[vout]" if use_captions else "0:v"]
    # Map audio: mixed stream if BGM, else original.
    cmd += ["-map", "[aout]" if use_bgm else "0:a"]

    # Video codec: re-encode if we drew captions, else copy.
    if use_captions:
        cmd += ["-c:v", "libx264", "-preset", "veryfast"]
    else:
        cmd += ["-c:v", "copy"]

    cmd += [
        "-c:a", "aac",
        "-shortest",
        "-loglevel", "error",
        "-y",
        str(out),
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    except subprocess.TimeoutExpired:
        raise VideoProbeError(f"ffmpeg timed out finalizing montage: {video_path}")

    if result.returncode != 0:
        raise VideoProbeError(f"ffmpeg failed finalizing montage: {result.stderr}")