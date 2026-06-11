"""
OCR detection service (EasyOCR-based).

Reads text from video frames to detect kill events. For LOL, the kill banner
appears near the top-center of the screen and contains the fixed substring
"击杀了" (e.g. "PlayerA 击杀了 PlayerB!").

The EasyOCR reader is heavy to initialize, so it is created once and reused.
"""

from functools import lru_cache

import easyocr


@lru_cache(maxsize=1)
def get_reader() -> easyocr.Reader:
    """
    Return a singleton EasyOCR reader (Chinese + English).

    Created lazily on first use and cached, because initializing the reader
    (loading models onto the GPU) is expensive and should happen only once.
    """
    # ch_sim handles the Chinese kill text; en catches latin player names.
    return easyocr.Reader(["ch_sim", "en"], gpu=True)


def read_text_from_image(image_path: str) -> list[str]:
    """
    Run OCR on an image and return all recognized text lines.

    Args:
        image_path: Path to the image file (a video frame).

    Returns:
        List of recognized text strings (may be empty).
    """
    reader = get_reader()
    results = reader.readtext(image_path)
    # readtext returns (bbox, text, confidence) tuples; we only need text.
    return [text for (_bbox, text, _conf) in results]


def contains_keyword(image_path: str, keyword: str) -> bool:
    """
    Check whether a given keyword appears in any text recognized in the image.

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