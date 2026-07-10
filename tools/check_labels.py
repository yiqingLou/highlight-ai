"""Draw YOLO label boxes back onto training images for visual QA.

Usage: python tools/check_labels.py
Renders every labeled training image with its boxes into
yolo/datasets/naraka/label_check/ for eyeballing.
"""
import os
import glob
import cv2

IMG_DIR = "yolo/datasets/naraka/images/train"
LBL_DIR = "yolo/datasets/naraka/labels/train"
OUT_DIR = "yolo/datasets/naraka/label_check"
os.makedirs(OUT_DIR, exist_ok=True)

count = 0
for lbl_path in sorted(glob.glob(f"{LBL_DIR}/*.txt")):
    stem = os.path.splitext(os.path.basename(lbl_path))[0]
    img_path = f"{IMG_DIR}/{stem}.jpg"
    if not os.path.exists(img_path):
        print("missing image for", stem)
        continue
    img = cv2.imread(img_path)
    h, w = img.shape[:2]
    with open(lbl_path) as f:
        for line in f:
            parts = line.split()
            if len(parts) != 5:
                print("BAD LINE in", stem, "->", line.strip())
                continue
            _, cx, cy, bw, bh = map(float, parts)
            x1 = int((cx - bw / 2) * w)
            y1 = int((cy - bh / 2) * h)
            x2 = int((cx + bw / 2) * w)
            y2 = int((cy + bh / 2) * h)
            cv2.rectangle(img, (x1, y1), (x2, y2), (0, 0, 255), 3)
    cv2.imwrite(f"{OUT_DIR}/{stem}.jpg", img)
    count += 1
print(f"rendered {count} labeled images to {OUT_DIR}")
