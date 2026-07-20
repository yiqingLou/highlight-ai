"""
Clip assembler service.

Cuts highlight segments out of the source video using ffmpeg. Each highlight
(start_sec -> end_sec) becomes its own short mp4 clip. Clips can then be
concatenated into a montage and have background music mixed over them.

MVP scope: cut, concat, and BGM mixing. No transitions or subtitles yet.
"""

import subprocess
from pathlib import Path
from typing import Optional

from app.paths import FFMPEG_EXE, FFPROBE_EXE
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
        FFMPEG_EXE,
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


def _probe_duration(path: str) -> float:
    """Return the duration of a media file in seconds using ffprobe."""
    probe = subprocess.run(
        [
            FFPROBE_EXE, "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    try:
        return float(probe.stdout.strip())
    except (ValueError, AttributeError):
        return 0.0


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
        FFMPEG_EXE,
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

    return [_probe_duration(p) for p in clip_paths]


def concat_clips_with_transitions(
    clip_paths: list[str],
    output_path: str,
    transition_duration: float = 0.5,
    transition_types: list[str] | None = None,
) -> list[float]:
    """Concatenate clips with crossfade transitions between them.

    Uses xfade (video) and acrossfade (audio) filter chains, so the output is
    re-encoded. Returns the real duration of each input clip (needed by the
    caption timeline, same contract as concat_clips).
    """
    if not clip_paths:
        raise ValueError("concat_clips_with_transitions: clip_paths is empty")

    for p in clip_paths:
        if not Path(p).exists():
            raise FileNotFoundError(f"Clip not found: {p}")

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    durations = [_probe_duration(p) for p in clip_paths]

    if len(clip_paths) == 1:
        # Single clip: nothing to transition, just copy.
        result = subprocess.run(
            [FFMPEG_EXE, "-nostdin", "-i", clip_paths[0],
             "-c", "copy", "-loglevel", "error", "-y", str(out)],
            capture_output=True,
            text=True,
            timeout=600,
        )
        if result.returncode != 0:
            raise VideoProbeError(
                f"ffmpeg failed copying single clip for transitions: {result.stderr}"
            )
        return durations

    inputs: list[str] = []
    for p in clip_paths:
        inputs += ["-i", p]

    td = transition_duration
    filter_parts: list[str] = []

    # Video xfade chain: [0][1] -> [v01], [v01][2] -> [v02], ...
    prev = "[0:v]"
    offset = durations[0] - td
    for i in range(1, len(clip_paths)):
        out_filter = f"[v{i:02d}]"
        ttype = "fade"
        if transition_types and i - 1 < len(transition_types):
            ttype = transition_types[i - 1]
        # Pro guideline: a flash must be 0.2-0.5s to read as a flash.
        seg_td = 0.4 if ttype in ("fadewhite", "fadeblack") else td
        filter_parts.append(
            f"{prev}[{i}:v]xfade=transition={ttype}:"
            f"duration={seg_td}:offset={offset:.3f}{out_filter}"
        )
        prev = out_filter
        offset += durations[i] - seg_td
    video_out = prev

    # Audio acrossfade chain, mirroring the video chain.
    prev_a = "[0:a]"
    for i in range(1, len(clip_paths)):
        out_a = f"[a{i:02d}]"
        filter_parts.append(f"{prev_a}[{i}:a]acrossfade=d={td}{out_a}")
        prev_a = out_a
    audio_out = prev_a

    cmd = (
        [FFMPEG_EXE, "-nostdin"] + inputs
        + ["-filter_complex", ";".join(filter_parts),
           "-map", video_out, "-map", audio_out,
           "-c:v", "libx264", "-preset", "fast", "-crf", "18",
           "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "192k",
           "-loglevel", "error", "-y", str(out)]
    )
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
    if result.returncode != 0:
        raise VideoProbeError(f"ffmpeg failed concatenating clips with transitions: {result.stderr}")
    return durations


def make_title_card(
    text: str,
    output_path: str,
    bg_image: Optional[str] = None,
    duration: float = 3.0,
    subtitle: Optional[str] = None,
    width: int = 2560,
    height: int = 1600,
    fps: int = 60,
) -> None:
    """Render an intro/outro title card as a video segment.

    A dimmed background (an image, slowly zoomed for a Ken Burns feel, or
    solid black if no image) with Bebas Neue title text that slides up and
    fades in, holds, then fades out. Output matches the montage clips'
    format (resolution / fps / yuv420p) so it can be concatenated with them.
    """
    font = "C\\:/Windows/Fonts/BebasNeue-Regular.ttf"
    total_frames = int(round(duration * fps))
    fade = 0.4  # seconds for text fade in / out

    # Text alpha: fade in over `fade`s, hold, fade out over the last `fade`s.
    alpha = (
        f"if(lt(t\\,{fade})\\,t/{fade}\\,"
        f"if(gt(t\\,{duration}-{fade})\\,({duration}-t)/{fade}\\,1))"
    )
    # Slide up: text starts 40px lower, eases to center during fade-in.
    y_main = f"(h-text_h)/2 + 40*(1-min(t/{fade}\\,1))"

    filters = []
    if bg_image:
        # Ken Burns: slow zoom from 1.0 to ~1.08 across the whole card.
        filters.append(
            f"zoompan=z='min(zoom+0.0008\\,1.08)':"
            f"d={total_frames}:s={width}x{height}:fps={fps}"
        )
        filters.append("eq=brightness=-0.35")  # dim the background
    filters.append(
        "drawtext="
        f"fontfile='{font}':"
        f"text='{text}':"
        "fontcolor=white:"
        "fontsize=h/8:"
        "shadowcolor=black@0.6:shadowx=3:shadowy=3:"
        f"alpha='{alpha}':"
        "x=(w-text_w)/2:"
        f"y={y_main}"
    )
    if subtitle:
        filters.append(
            "drawtext="
            f"fontfile='{font}':"
            f"text='{subtitle}':"
            "fontcolor=white@0.85:"
            "fontsize=h/22:"
            f"alpha='{alpha}':"
            "x=(w-text_w)/2:"
            "y=(h-text_h)/2+h/9"
        )
    vf = ",".join(filters)

    if bg_image:
        cmd = [
            FFMPEG_EXE, "-nostdin",
            "-loop", "1", "-t", str(duration), "-i", bg_image,
            "-f", "lavfi", "-t", str(duration),
            "-i", "anullsrc=channel_layout=stereo:sample_rate=48000",
            "-vf", vf,
            "-r", str(fps), "-pix_fmt", "yuv420p",
            "-c:v", "libx264", "-preset", "fast", "-crf", "18",
            "-c:a", "aac", "-b:a", "192k",
            "-loglevel", "error", "-y", output_path,
        ]
    else:
        # Solid black background source.
        cmd = [
            FFMPEG_EXE, "-nostdin",
            "-f", "lavfi", "-i",
            f"color=c=black:s={width}x{height}:r={fps}:d={duration}",
            "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=48000",
            "-vf", vf, "-t", str(duration),
            "-pix_fmt", "yuv420p",
            "-c:v", "libx264", "-preset", "fast", "-crf", "18",
            "-shortest", "-c:a", "aac", "-b:a", "192k",
            "-loglevel", "error", "-y", output_path,
        ]
    subprocess.run(cmd, check=True, timeout=300)


def apply_kill_slowmo(
    clip_path: str,
    output_path: str,
    kill_sec: float,
    fps: int = 60,
    sfx_path: Optional[str] = None,
) -> None:
    """Apply a speed-ramp slow motion leading into the kill moment.

    The window (kill_sec - 1.2) .. (kill_sec - 0.5) ramps down through
    five speed steps (0.9 -> 0.4) with motion interpolation, then playback
    returns to normal speed 0.5s BEFORE the kill so the kill itself hits
    at full speed. Audio is tempo-stretched per segment to stay in sync
    (slowed audio drops in pitch, which suits the effect).
    """
    ramp_end = kill_sec - 0.5     # normal speed resumes here
    ramp_start = ramp_end - 1.2   # total ramp window: 1.2s of source

    # (offset_from_start, duration, speed) — mirrors the approved test.
    steps = [
        (0.0, 0.2, 0.90),
        (0.2, 0.2, 0.75),
        (0.4, 0.2, 0.60),
        (0.6, 0.3, 0.50),
        (0.9, 0.3, 0.40),
    ]

    v_parts, v_labels = [], []

    # Normal head.
    v_parts.append(f"[0:v]trim=0:{ramp_start:.3f},setpts=PTS-STARTPTS[v0]")
    v_labels.append("[v0]")

    for i, (off, dur, speed) in enumerate(steps, start=1):
        a1 = ramp_start + off
        b1 = a1 + dur
        v_parts.append(
            f"[0:v]trim={a1:.3f}:{b1:.3f},setpts=(PTS-STARTPTS)/{speed},"
            f"minterpolate=fps={fps}:mi_mode=mci:mc_mode=aobmc:me_mode=bidir"
            f"[v{i}]"
        )
        v_labels.append(f"[v{i}]")

    # Normal tail (the kill plays at full speed).
    n = len(steps) + 1
    v_parts.append(f"[0:v]trim={ramp_end:.3f},setpts=PTS-STARTPTS[v{n}]")
    v_labels.append(f"[v{n}]")

    # --- Audio: 3 segments (normal head / slow-mo bed / normal tail) ---
    slow_total = sum(d / s for _, d, s in steps)  # stretched duration

    a_parts = []
    a_parts.append(
        f"[0:a]atrim=0:{ramp_start:.3f},asetpts=PTS-STARTPTS,"
        f"afade=t=out:st={ramp_start-0.3:.3f}:d=0.3[ah]"
    )
    if sfx_path:
        # Bass drop bed under the slow-mo (padded/trimmed to fit).
        a_parts.append(
            f"[1:a]atrim=0:{slow_total:.3f},asetpts=PTS-STARTPTS,"
            f"volume=0.9,apad=whole_dur={slow_total:.3f}[as]"
        )
    else:
        a_parts.append(
            f"anullsrc=channel_layout=stereo:sample_rate=48000,"
            f"atrim=0:{slow_total:.3f}[as]"
        )
    a_parts.append(
        f"[0:a]atrim={ramp_end:.3f},asetpts=PTS-STARTPTS,"
        f"afade=t=in:st=0:d=0.15[at]"
    )

    fc = (
        ";".join(v_parts) + ";" + ";".join(a_parts) + ";"
        + "".join(v_labels) + f"concat=n={n+1}:v=1:a=0[outv];"
        + "[ah][as][at]concat=n=3:v=0:a=1[outa]"
    )

    inputs = ["-i", clip_path]
    if sfx_path:
        inputs += ["-i", sfx_path]
    cmd = [FFMPEG_EXE, "-nostdin"] + inputs + [
        "-filter_complex", fc,
        "-map", "[outv]", "-map", "[outa]",
        "-r", str(fps), "-pix_fmt", "yuv420p",
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-c:a", "aac", "-b:a", "192k",
        "-loglevel", "error", "-y", output_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
    if result.returncode != 0:
        raise VideoProbeError(
            f"ffmpeg failed applying kill slow-mo: {result.stderr}"
        )


def add_bgm(
    video_path: str,
    output_path: str,
    bgm_path: str | None = None,
    original_volume: float = 0.45,
    bgm_volume: float = 0.8,
    captions: list[dict] | None = None,
    bgm_offset_sec: float = 0.0,
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
            FFMPEG_EXE, "-nostdin",
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

    cmd = [FFMPEG_EXE, "-nostdin", "-i", str(src)]
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
            f"[1:a]atrim=start={bgm_offset_sec:.3f},asetpts=PTS-STARTPTS,"
            f"volume={bgm_volume}[a1];"
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


def export_vertical(input_path: str, output_path: str) -> None:
    """Re-frame a landscape montage into 1080x1920 for TikTok/Shorts.

    The source is centered at full width; the gaps above and below are
    filled with a blurred, zoomed copy of the same frame so nothing is
    cropped away and the result never shows black bars.
    """
    filter_complex = (
        "[0:v]split=2[bg][fg];"
        "[bg]scale=1080:1920:force_original_aspect_ratio=increase,"
        "crop=1080:1920,gblur=sigma=28[bgblur];"
        "[fg]scale=1080:-2[fgs];"
        "[bgblur][fgs]overlay=(W-w)/2:(H-h)/2"
    )
    cmd = [
        FFMPEG_EXE, "-nostdin", "-y",
        "-i", input_path,
        "-filter_complex", filter_complex,
        "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-pix_fmt", "yuv420p",
        "-c:a", "copy",
        output_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise VideoProbeError(f"Vertical export failed: {result.stderr[-500:]}")