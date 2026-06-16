"""
League of Legends (LOL) game profile.

Detects YOUR OWN kills by reading the center-screen first-person kill banners
with OCR. For the Chinese (国服) client, these banners appear ONLY for your
own kills (the bottom-left kill feed showing other players is excluded by the
OCR crop region in ocr_detector).

Two layers of detection:
  Layer 1 (anchor): "你已经击杀" = you got a kill. This is the reliable signal.
  Layer 2 (upgrade): "双杀"/"三杀"/"四杀"/"五杀"/"终结" appear center-screen during
      multi-kills. Because the crop excludes the kill feed, a multi-kill word in
      the cropped region belongs to YOU. We use it to upgrade the highlight's
      label and score (a triple kill is more exciting than a single kill).

Detection strategy:
    Run OCR on every frame and record which keyword(s) hit and when. Consecutive
    hits (banners persist for seconds) are GROUPED into one kill event; a new
    event starts only after a gap of >= GAP_SECONDS with no hits. Each group
    becomes one highlight, labelled/scored by the HIGHEST-tier keyword in it.
"""

from .base import GameProfile, DetectedHighlight
from app.services.ocr_detector import contains_keyword


class LolProfile(GameProfile):
    """Game profile for League of Legends (Chinese client)."""

    game_id = "lol"
    display_name = "League of Legends"

    # Anchor keyword: presence means "you got a kill".
    SINGLE_KILL_KEYWORD = "你已经击杀"

    # Multi-kill / special kill keywords -> (label, score). Higher tier = more
    # exciting. Because the OCR crop excludes the bottom-left kill feed, these
    # center-screen words belong to the player. Order does not matter here; we
    # pick the highest-scoring one found in a group.
    KILL_TIERS = {
        "你已经击杀": ("kill", 90),
        "双杀": ("double_kill", 93),
        "三杀": ("triple_kill", 96),
        "四杀": ("quadra_kill", 98),
        "五杀": ("penta_kill", 100),
        "终结": ("shutdown", 95),
    }

    # All keywords to scan for (anchor + all tiers).
    KILL_KEYWORDS = list(KILL_TIERS.keys())

    # A new kill event starts only after this many seconds with no hits.
    GAP_SECONDS = 5.0

    # Clip length around each detected kill.
    CLIP_DURATION = 8.0

    def detect_highlights(
        self,
        frame_paths: list[str],
        fps: float,
    ) -> list[DetectedHighlight]:
        """
        Detect your kills (with multi-kill upgrade) by OCR-scanning frames.

        Args:
            frame_paths: Ordered list of extracted frame image paths.
            fps: Extraction fps (frames sampled per second), used to convert
                 frame index to a timestamp.

        Returns:
            List of DetectedHighlight (one per kill event), sorted by center_sec.
        """
        if not frame_paths:
            return []

        # 1. For each frame, record (timestamp, set of keywords found).
        #    A frame may contain more than one keyword (e.g. "你已经击杀" and
        #    "双杀" could co-occur), so we collect all matches.
        hits: list[tuple[float, set[str]]] = []
        for frame_index, frame_path in enumerate(frame_paths):
            found = {
                kw for kw in self.KILL_KEYWORDS
                if contains_keyword(frame_path, kw)
            }
            if found:
                sec = self.frame_index_to_sec(frame_index, fps)
                hits.append((sec, found))

        if not hits:
            return []

        # 2. Group consecutive hits into kill events (gap >= GAP_SECONDS splits).
        groups: list[list[tuple[float, set[str]]]] = []
        current: list[tuple[float, set[str]]] = [hits[0]]
        for sec, found in hits[1:]:
            if sec - current[-1][0] >= self.GAP_SECONDS:
                groups.append(current)
                current = [(sec, found)]
            else:
                current.append((sec, found))
        groups.append(current)

        # 3. One highlight per group; label/score by the highest-tier keyword.
        highlights: list[DetectedHighlight] = []
        for group in groups:
            times = [sec for sec, _ in group]
            center_sec = (times[0] + times[-1]) / 2

            # Collect every keyword seen anywhere in this group.
            all_keywords: set[str] = set()
            for _, found in group:
                all_keywords |= found

            # Pick the highest-scoring keyword as this event's tier.
            best_kw = max(all_keywords, key=lambda kw: self.KILL_TIERS[kw][1])
            label, score = self.KILL_TIERS[best_kw]

            highlights.append(
                DetectedHighlight(
                    center_sec=round(center_sec, 2),
                    duration_sec=self.CLIP_DURATION,
                    kind=label,
                    confidence=round(score / 100, 2),
                    meta={
                        "source": "ocr",
                        "tier": label,
                        "score": score,
                        "keywords": sorted(all_keywords),
                        "hit_count": len(group),
                        "first_hit_sec": round(times[0], 2),
                        "last_hit_sec": round(times[-1], 2),
                    },
                )
            )

        highlights.sort(key=lambda h: h.center_sec)
        return highlights