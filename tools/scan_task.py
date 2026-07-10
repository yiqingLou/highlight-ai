"""Low-confidence scan of a task's extracted frames.

Usage: python tools/scan_task.py <task_id> [conf] [model_path]
Prints every frame with a detection above the given confidence.
"""
import sys

sys.path.insert(0, "backend")
from ultralytics import YOLO
import glob

task_id = sys.argv[1]
conf = float(sys.argv[2]) if len(sys.argv) > 2 else 0.1
model_path = sys.argv[3] if len(sys.argv) > 3 else "ml/models/naraka_kill.pt"

model = YOLO(model_path)
frames = sorted(glob.glob(f"backend/frames/{task_id}/*.jpg"))
print(f"task {task_id}: {len(frames)} frames, model={model_path}, conf={conf}")
for i, f in enumerate(frames):
    r = model(f, conf=conf, verbose=False)[0]
    if len(r.boxes) > 0:
        print(f"t={i+1}s  conf={float(r.boxes.conf.max()):.3f}")
print("scan done")
