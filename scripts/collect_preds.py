import shutil
from pathlib import Path

PRED_DIR = Path("runs/detect/predict-6")
PRED_LABELS_DIR = PRED_DIR / "labels"
REVIEW_DIR = PRED_DIR / "_review"
IMAGE_EXTS = (".jpg", ".jpeg", ".png")

REVIEW_DIR.mkdir(parents=True, exist_ok=True)
copied = 0
for label_path in sorted(PRED_LABELS_DIR.glob("*.txt")):
    stem = label_path.stem
    for ext in IMAGE_EXTS:
        src = PRED_DIR / (stem + ext)
        if src.exists():
            shutil.copy2(src, REVIEW_DIR / src.name)
            copied += 1
            break
print("Copied", copied, "boxed frames to", REVIEW_DIR)
