"""Batch-scan gameplay videos for kill detections, without touching the app DB.

Usage (run from project root, yolo venv):
    python tools\batch_scan.py <videos_dir> [conf] [model_path] [fps]

fps defaults to 1. With fps=2 frames land in <name>_fps2/ and times are
reported at half-second resolution - used to probe sampling-gap misses.
"""
import subprocess
import sys
from pathlib import Path

import cv2
from ultralytics import YOLO

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FFMPEG = PROJECT_ROOT / "backend" / "bin" / "ffmpeg.exe"
WORK = PROJECT_ROOT / "batch_scan_work"


def extract_frames(video, frames_dir, fps):
    frames_dir.mkdir(parents=True, exist_ok=True)
    existing = list(frames_dir.glob("frame_*.jpg"))
    if existing:
        print(f"  frames already there ({len(existing)}), skipping extraction")
        return
    cmd = [
        str(FFMPEG), "-nostdin", "-y",
        "-i", str(video),
        "-vf", f"fps={fps}",
        "-qscale:v", "2",
        str(frames_dir / "frame_%05d.jpg"),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed on {video.name}: {result.stderr[-300:]}")


def scan_video(model, video, conf, fps, summary_lines):
    name = video.stem if fps == 1 else f"{video.stem}_fps{fps:g}"
    vdir = WORK / name
    frames_dir = vdir / "frames"
    review_dir = vdir / "review"
    review_dir.mkdir(parents=True, exist_ok=True)

    print(f"[{name}] extracting frames at fps={fps:g}...")
    extract_frames(video, frames_dir, fps)

    frames = sorted(frames_dir.glob("frame_*.jpg"))
    print(f"[{name}] scanning {len(frames)} frames at conf={conf}")

    hits = []
    for frame in frames:
        results = model(str(frame), conf=conf, verbose=False)
        boxes = results[0].boxes
        if boxes is None or len(boxes) == 0:
            continue
        idx = int(frame.stem.split("_")[1])
        t = idx / fps
        best = float(boxes.conf.max())
        hits.append((t, best))
        annotated = results[0].plot()
        cv2.imwrite(str(review_dir / f"hit_{t:07.1f}_{best:.2f}.jpg"), annotated)

    report = vdir / "report.txt"
    with open(report, "w", encoding="utf-8") as f:
        f.write(f"{video.name}: {len(frames)} frames, conf={conf}, fps={fps:g}\n")
        for t, c in hits:
            f.write(f"t={t:.1f}s  conf={c:.3f}\n")
    print(f"[{name}] {len(hits)} hits -> {report}")
    summary_lines.append(f"{name}: {len(hits)} hits / {len(frames)} frames")


def main():
    if len(sys.argv) < 2:
        print("usage: python tools\\batch_scan.py <videos_dir> [conf] [model_path] [fps]")
        sys.exit(1)
    videos_dir = Path(sys.argv[1])
    conf = float(sys.argv[2]) if len(sys.argv) > 2 else 0.35
    model_path = sys.argv[3] if len(sys.argv) > 3 else str(
        PROJECT_ROOT / "ml" / "models" / "naraka_kill.pt")
    fps = float(sys.argv[4]) if len(sys.argv) > 4 else 1.0

    videos = sorted(videos_dir.glob("*.mp4"))
    if not videos:
        print(f"no .mp4 files found in {videos_dir}")
        sys.exit(1)

    print(f"batch scan: {len(videos)} videos, model={model_path}, fps={fps:g}")
    model = YOLO(model_path)
    WORK.mkdir(exist_ok=True)

    summary_lines = []
    for video in videos:
        scan_video(model, video, conf, fps, summary_lines)

    with open(WORK / "summary.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(summary_lines) + "\n")
    print("\n=== summary ===")
    for line in summary_lines:
        print(line)


if __name__ == "__main__":
    main()