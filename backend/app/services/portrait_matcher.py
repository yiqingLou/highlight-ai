"""
Portrait matcher service (method C: attribute multi-kills to the player).

Problem: LoL multi-kill banners ("双杀"/"三杀"/"终结") are broadcast to everyone's
screen for ANY player's multi-kill, so the keyword alone cannot tell whose kill
it is. But the multi-kill banner shows the KILLER's champion portrait, and the
bottom HUD always shows YOUR champion portrait. If the banner's killer portrait
is the same champion as your HUD portrait, the multi-kill is YOURS.

Matching technique: direct template matching (cv2.matchTemplate) does NOT work
here, because the banner portrait and HUD portrait are the same champion but
framed/zoomed/angled differently. HSV colour-histogram correlation DOES work:
empirically same-champion ~0.81 vs different-champion ~0.27, so a threshold
around 0.55 cleanly separates them.

NOTE: crop regions are fractions tuned for the 2560x1600 client. They should
hold for other resolutions (fixed UI layout) but verify if results look off.
"""

import cv2

# --- Crop regions as (y0, y1, x0, x1) fractions of the frame ---
# Bottom-center HUD: YOUR champion portrait (always present, always you).
HUD_PORTRAIT_REGION = (0.878, 0.945, 0.277, 0.323)
# Multi-kill banner, LEFT portrait: the champion who got the multi-kill.
BANNER_PORTRAIT_REGION = (0.115, 0.175, 0.428, 0.468)

# Same-champion if histogram correlation >= this. Tuned from 0.81 vs 0.27 margin.
MATCH_THRESHOLD = 0.55


def _crop(image, region):
    """Crop an image by (y0, y1, x0, x1) fractions."""
    h, w = image.shape[:2]
    y0, y1, x0, x1 = region
    return image[int(h * y0):int(h * y1), int(w * x0):int(w * x1)]


def _hsv_hist(patch):
    """HSV hue-saturation histogram of a patch (resized for scale invariance)."""
    hsv = cv2.cvtColor(cv2.resize(patch, (64, 64)), cv2.COLOR_BGR2HSV)
    hist = cv2.calcHist([hsv], [0, 1], None, [50, 60], [0, 180, 0, 256])
    cv2.normalize(hist, hist).flatten()
    return hist


def portrait_similarity(image_path: str) -> float:
    """
    Compare the multi-kill banner's killer portrait to the HUD (player) portrait.

    Args:
        image_path: Path to a frame that contains a multi-kill banner.

    Returns:
        Histogram correlation in [-1, 1]; higher = more likely the same champion
        (i.e. the multi-kill is the player's). Returns -1.0 if the image is
        unreadable.
    """
    image = cv2.imread(image_path)
    if image is None:
        return -1.0
    hud = _hsv_hist(_crop(image, HUD_PORTRAIT_REGION))
    banner = _hsv_hist(_crop(image, BANNER_PORTRAIT_REGION))
    return float(cv2.compareHist(hud, banner, cv2.HISTCMP_CORREL))


def is_player_multikill(image_path: str) -> bool:
    """
    Return True if the multi-kill banner in this frame belongs to the player
    (banner killer portrait matches the HUD champion portrait).
    """
    return portrait_similarity(image_path) >= MATCH_THRESHOLD