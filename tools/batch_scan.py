"""Batch-scan gameplay videos for kill detections, without touching the app DB.

Usage (run from project root, yolo venv):
    python tools\batch_scan.py <videos_dir> [conf] [model_path]

For every .mp4 in <videos_dir> this script:
  1. extracts 1fps frames into batch_scan_work/<name>/frames
  2. runs the model over every frame at the given confidence
  3. writes batch_scan_work/<name>/report.txt  (t=..s conf=..)
  4. saves annotated hit frames into batch_scan_work/<name>/review
A combined overview lands in batch_scan_work/summary.txt.
"""

import subprocess
import sys
from pathlib import Path

import cv2
from ultralytics import YOLO

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.paths import FFMPEG_EXE, MODELS_DIR

WORK = PROJECT_ROOT / "batch_scan_work"


def extract_frames(video: Path, frames_dir: Path) -> None:
    frames_dir.mkdir(parents=True, exist_ok=True)
    existing = list(frames_dir.glob("frame_*.jpg"))
    if existing:
        print(f"  frames already there ({len(existing)}), skipping extraction")
        return

    cmd = [
        FFMPEG_EXE,
        "-nostdin",
        "-y",
        "-i",
        str(video),
        "-vf",
        "fps=1",
        "-qscale:v",
        "2",
        str(frames_dir / "frame_%04d.jpg"),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed on {video.name}: {result.stderr[-300:]}")


def scan_video(model: YOLO, video: Path, conf: float, summary_lines: list[str]) -> None:
    name = video.stem
    vdir = WORK / name
    frames_dir = vdir / "frames"
    review_dir = vdir / "review"
    review_dir.mkdir(parents=True, exist_ok=True)

    print(f"[{name}] extracting frames...")
    extract_frames(video, frames_dir)

    frames = sorted(frames_dir.glob("frame_*.jpg"))
    print(f"[{name}] scanning {len(frames)} frames at conf={conf}")

    hits: list[tuple[int, float]] = []
    for frame in frames:
        results = model(str(frame), conf=conf, verbose=False)
        boxes = results[0].boxes
        if boxes is None or len(boxes) == 0:
            continue

        second = int(frame.stem.split("_")[1])
        best = float(boxes.conf.max())
        hits.append((second, best))

        annotated = results[0].plot()
        cv2.imwrite(str(review_dir / f"hit_{second:04d}_{best:.2f}.jpg"), annotated)

    report = vdir / "report.txt"
    with open(report, "w", encoding="utf-8") as f:
        f.write(f"{video.name}: {len(frames)} frames, conf={conf}\n")
        for second, score in hits:
            f.write(f"t={second}s  conf={score:.3f}\n")

    print(f"[{name}] {len(hits)} hits -> {report}")
    summary_lines.append(f"{name}: {len(hits)} hits / {len(frames)} frames")


def main() -> None:
    if len(sys.argv) < 2:
        print("usage: python tools\\batch_scan.py <videos_dir> [conf] [model_path]")
        sys.exit(1)

    videos_dir = Path(sys.argv[1])
    conf = float(sys.argv[2]) if len(sys.argv) > 2 else 0.35
    model_path = sys.argv[3] if len(sys.argv) > 3 else str(MODELS_DIR / "naraka_kill.pt")

    videos = sorted(videos_dir.glob("*.mp4"))
    if not videos:
        print(f"no .mp4 files found in {videos_dir}")
        sys.exit(1)

    print(f"batch scan: {len(videos)} videos, model={model_path}")
    model = YOLO(model_path)
    WORK.mkdir(exist_ok=True)

    summary_lines: list[str] = []
    for video in videos:
        scan_video(model, video, conf, summary_lines)

    with open(WORK / "summary.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(summary_lines) + "\n")

    print("\n=== summary ===")
    for line in summary_lines:
        print(line)


if __name__ == "__main__":
    main()