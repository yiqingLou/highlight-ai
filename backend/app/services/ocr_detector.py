"""
OCR detection service (EasyOCR-based).

Reads text from video frames to detect kill events. For LOL, the kill banner
appears near the top-center of the screen and contains the fixed substring
"击杀了" (e.g. "PlayerA 击杀了 PlayerB!").

Performance: instead of OCR-ing the full frame, we crop to the top-center
region where the kill banner appears. This is much faster (far fewer pixels)
and more accurate (ignores unrelated on-screen text). Crop bounds are given
as fractions so they adapt to any resolution.

The EasyOCR reader is heavy to initialize, so it is created once and reused.
"""

from functools import lru_cache

import cv2
import easyocr

# Crop region for the kill banner, as fractions of width/height.
# Generous bounds (top-center) to avoid missing the banner across resolutions.
CROP_TOP = 0.10      # start 10% down from the top
CROP_BOTTOM = 0.35   # end 35% down
CROP_LEFT = 0.25     # start 25% from the left
CROP_RIGHT = 0.75    # end 75% from the left


@lru_cache(maxsize=1)
def get_reader() -> easyocr.Reader:
    """
    Return a singleton EasyOCR reader (Chinese + English).

    Created lazily on first use and cached, because initializing the reader
    (loading models onto the GPU) is expensive and should happen only once.
    """
    # ch_sim handles the Chinese kill text; en catches latin player names.
    return easyocr.Reader(["ch_sim", "en"], gpu=True)


def _crop_kill_region(image):
    """
    Crop an image (numpy array) to the top-center kill-banner region.

    Args:
        image: BGR image as a numpy array (from cv2.imread).

    Returns:
        Cropped image (numpy array). Falls back to the full image if the
        crop would be empty for some reason.
    """
    height, width = image.shape[:2]
    top = int(height * CROP_TOP)
    bottom = int(height * CROP_BOTTOM)
    left = int(width * CROP_LEFT)
    right = int(width * CROP_RIGHT)

    cropped = image[top:bottom, left:right]
    # Safety: if crop is empty, use the full image instead.
    if cropped.size == 0:
        return image
    return cropped


def read_text_from_image(image_path: str) -> list[str]:
    """
    Run OCR on the kill-banner region of an image and return recognized text.

    Args:
        image_path: Path to the image file (a video frame).

    Returns:
        List of recognized text strings (may be empty).
    """
    image = cv2.imread(image_path)
    if image is None:
        # Could not read the image; nothing to OCR.
        return []

    region = _crop_kill_region(image)

    reader = get_reader()
    # Pass the cropped numpy array directly to readtext.
    results = reader.readtext(region)
    # readtext returns (bbox, text, confidence) tuples; we only need text.
    return [text for (_bbox, text, _conf) in results]


def contains_keyword(image_path: str, keyword: str) -> bool:
    """
    Check whether a given keyword appears in any text recognized in the
    kill-banner region of the image.

    Args:
        image_path: Path to the image file.
        keyword: Substring to look for (e.g. "击杀了").

    Returns:
        True if the keyword is found in any recognized text line.
    """
    for text in read_text_from_image(image_path):
        if keyword in text:
            return True
    return False