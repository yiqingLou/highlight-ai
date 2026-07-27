"""Pick the fastest available H.264 encoder once, at startup.

NVENC (GPU hardware encoding) cuts encode times by 5-10x on NVIDIA cards;
machines without one fall back to libx264 transparently.
"""
import subprocess

from app.paths import FFMPEG_EXE

_NV_PRESET = {"veryfast": "p3", "fast": "p4", "medium": "p5"}


def _nvenc_available() -> bool:
    """Probe by encoding 0.1s of nothing; returncode 0 means NVENC works."""
    try:
        r = subprocess.run(
            [FFMPEG_EXE, "-hide_banner",
             "-f", "lavfi", "-i", "nullsrc=s=256x256:d=0.1",
             "-c:v", "h264_nvenc", "-f", "null", "-"],
            capture_output=True, text=True, timeout=15,
        )
        return r.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


NVENC = _nvenc_available()


def video_codec_args(crf: int = 20, preset: str = "medium") -> list:
    """Drop-in replacement for the old libx264 flag blocks."""
    if NVENC:
        return ["-c:v", "h264_nvenc", "-preset", _NV_PRESET.get(preset, "p4"),
                "-cq", str(crf), "-b:v", "0"]
    return ["-c:v", "libx264", "-preset", preset, "-crf", str(crf)]
