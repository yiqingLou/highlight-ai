"""Snowball step: merge verified predictions into the YOLO training set.

For each auto-predicted kill label that passed the manual check, copy the
label file and its frame image into images/train and labels/train.

The frames flagged as FALSE positives are NOT discarded: they are copied in
as background images (image only, no label) so the model learns those spots
are not scratches. This is the most effective way to cut false positives.

Run from the highlight-ai project root.
"""

import shutil
from pathlib import Path

# --- Config: paths are relative to the highlight-ai project root ----------
DATASET_ROOT = Path("yolo/datasets/naraka")
PRED_LABELS_DIR = Path("runs/detect/predict-6/labels")        # model predictions
FRAMES_DIR = DATASET_ROOT / "frames" / "scan_self"            # source frame images
TRAIN_IMAGES_DIR = DATASET_ROOT / "images" / "train"
TRAIN_LABELS_DIR = DATASET_ROOT / "labels" / "train"
IMAGE_EXTS = (".jpg", ".jpeg", ".png")

# Label stems (filename WITHOUT .txt) the manual check marked as false
# positives: the model boxed a center buff/event icon, not a kill scratch.
# These are copied in as background images (hard negatives).
FALSE_POSITIVES = {
    "s_0266",
    "s_0705",
    "s_0970",
    "s_0981",
    "s_0984",
}

# True  -> copy false-positive frames in as background images (recommended).
# False -> just drop them.
ADD_FALSE_POSITIVES_AS_BACKGROUND = True
# --------------------------------------------------------------------------


def find_image(stem):
    """Return the frame image matching the label stem, or None."""
    for ext in IMAGE_EXTS:
        candidate = FRAMES_DIR / f"{stem}{ext}"
        if candidate.exists():
            return candidate
    return None


def main():
    TRAIN_IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    TRAIN_LABELS_DIR.mkdir(parents=True, exist_ok=True)

    pred_labels = sorted(PRED_LABELS_DIR.glob("*.txt"))
    print(f"Found {len(pred_labels)} prediction labels in {PRED_LABELS_DIR}")

    added_pos, added_bg, skipped, missing = 0, 0, 0, 0

    for label_path in pred_labels:
        stem = label_path.stem
        image_path = find_image(stem)
        if image_path is None:
            missing += 1
            print(f"  [WARN] no image for {stem}, skipped")
            continue

        dst_image = TRAIN_IMAGES_DIR / image_path.name
        dst_label = TRAIN_LABELS_DIR / label_path.name

        # False positive -> background image (image only, no label).
        if stem in FALSE_POSITIVES:
            if not ADD_FALSE_POSITIVES_AS_BACKGROUND:
                print(f"  [drop] {stem} (false positive)")
                continue
            if not dst_image.exists():
                shutil.copy2(image_path, dst_image)
                added_bg += 1
                print(f"  [bg]   {stem} (hard negative)")
            else:
                skipped += 1
            if dst_label.exists():
                dst_label.unlink()  # ensure no stale label remains
            continue

        # Verified true positive -> copy both image and label.
        if dst_image.exists() and dst_label.exists():
            skipped += 1
            continue
        shutil.copy2(image_path, dst_image)
        shutil.copy2(label_path, dst_label)
        added_pos += 1
        print(f"  [add]  {stem}")

    total_labels = len(list(TRAIN_LABELS_DIR.glob("*.txt")))
    total_images = sum(len(list(TRAIN_IMAGES_DIR.glob(f"*{e}"))) for e in IMAGE_EXTS)

    print("\n=== Summary ===")
    print(f"true positives added: {added_pos}  (expect 22)")
    print(f"background added:     {added_bg}  (expect 5)")
    print(f"already in train:     {skipped}")
    print(f"image missing:        {missing}")
    print(f"train labels now:     {total_labels}  (expect 60)")
    print(f"train images now:     {total_images}  (expect 79)")


if __name__ == "__main__":
    main()