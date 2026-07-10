"""Render annotated frames for manual review of low-confidence detections.

Usage: python tools/review_task.py <task_id> <frame_numbers...>
Saves boxed frames to backend/frames/review<task_id>/ for eyeballing.
"""
import sys
import os

sys.path.insert(0, "backend")
from ultralytics import YOLO


task_id = sys.argv[1]
nums = [int(n) for n in sys.argv[2:]]

model = YOLO("ml/models/naraka_kill.pt")
src = f"backend/frames/{task_id}"
out = f"backend/frames/review{task_id}"
os.makedirs(out, exist_ok=True)

for n in nums:
    f = f"{src}/frame_{n:04d}.jpg"
    if not os.path.exists(f):
        print("missing:", f)
        continue
    r = model(f, conf=0.1, verbose=False)[0]
    r.save(f"{out}/hit_{n:04d}.jpg")
print(f"saved {len(nums)} annotated frames to {out}")
