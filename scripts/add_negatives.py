import random, shutil
from pathlib import Path

FRAMES_DIR = Path("yolo/datasets/naraka/frames/scan_self")
TRAIN_IMAGES_DIR = Path("yolo/datasets/naraka/images/train")
VERIFY_LABELS_DIR = Path("runs/detect/verify-3/labels")
N_RANDOM = 30
SEED = 42
CONFIRMED_FP = ["s_0074", "s_0157", "s_0286", "s_0921"]
IMAGE_EXTS = (".jpg", ".jpeg", ".png")

def stem_set(d):
    return {p.stem for p in d.glob("*") if p.suffix.lower() in IMAGE_EXTS}

already = stem_set(TRAIN_IMAGES_DIR)
boxed = {p.stem for p in VERIFY_LABELS_DIR.glob("*.txt")}
all_frames = stem_set(FRAMES_DIR)
candidates = sorted(all_frames - already - boxed)
print("total frames:", len(all_frames), "already in train:", len(already), "boxed by model:", len(boxed))
print("clean negative candidates:", len(candidates))

random.seed(SEED)
picked = random.sample(candidates, min(N_RANDOM, len(candidates)))
to_add = picked + [s for s in CONFIRMED_FP if s not in already]

added = 0
for stem in to_add:
    for ext in IMAGE_EXTS:
        src = FRAMES_DIR / (stem + ext)
        if src.exists():
            dst = TRAIN_IMAGES_DIR / src.name
            if not dst.exists():
                shutil.copy2(src, dst)
                added += 1
            break
print("background images added:", added)
total_images = sum(len(list(TRAIN_IMAGES_DIR.glob("*" + e))) for e in IMAGE_EXTS)
total_labels = len(list(Path("yolo/datasets/naraka/labels/train").glob("*.txt")))
print("train images now:", total_images)
print("train labels now:", total_labels)
