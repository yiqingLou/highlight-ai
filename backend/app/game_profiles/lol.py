"""
League of Legends (LOL) game profile.

Detects YOUR OWN kills by reading the center-screen first-person kill banner
with OCR. For the Chinese (国服) client this banner reads
"你已经击杀了一名敌方英雄！" and appears ONLY when you get a kill.

Why not the keyword "击杀了"? Because the bottom-left kill feed shows EVERY
player's kills ("Berdinox击杀了Gogeta UI"), plus "友方被杀" (ally died). Those
are not your highlights. The center first-person banner ("你已经击杀") is the
reliable signal that the kill is YOURS. The OCR crop region (top-center, set
in ocr_detector) also physically excludes the bottom-left kill feed.

Detection strategy:
    Run OCR on every frame and mark which frames contain the kill keyword.
    The banner stays on screen for several seconds, so many consecutive
    frames hit. We GROUP consecutive hits into one kill event: a new event
    only starts after a gap of >= GAP_SECONDS with no hits.
"""

from .base import GameProfile, DetectedHighlight
from app.services.ocr_detector import contains_keyword


class LolProfile(GameProfile):
    """Game profile for League of Legends (Chinese client)."""

    game_id = "lol"
    display_name = "League of Legends"

    # Center-screen first-person kill banner(s) = YOUR kill.
    # Use a short substring ("你已经击杀") to tolerate OCR dropping the tail
    # ("了一名敌方英雄！"). Do NOT use the broad "击杀了" — the kill feed is
    # full of other players' kills. Multi-kill upgrade (双杀/三杀) is a future
    # second layer, gated behind this anchor.
    KILL_KEYWORDS = ["你已经击杀"]

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
        Detect your kills by OCR-scanning frames and grouping consecutive hits.

        Args:
            frame_paths: Ordered list of extracted frame image paths.
            fps: Extraction fps (frames sampled per second), used to convert
                 frame index to a timestamp.

        Returns:
            List of DetectedHighlight (one per kill event), sorted by center_sec.
        """
        if not frame_paths:
            return []

        # 1. Find timestamps of all frames that contain a kill keyword.
        hit_times: list[float] = []
        for frame_index, frame_path in enumerate(frame_paths):
            hit = any(
                contains_keyword(frame_path, kw)
                for kw in self.KILL_KEYWORDS
            )
            if hit:
                hit_times.append(self.frame_index_to_sec(frame_index, fps))

        if not hit_times:
            return []

        # 2. Group consecutive hits into kill events.
        #    A gap >= GAP_SECONDS between two hits starts a new event.
        groups: list[list[float]] = []
        current_group: list[float] = [hit_times[0]]
        for t in hit_times[1:]:
            if t - current_group[-1] >= self.GAP_SECONDS:
                groups.append(current_group)
                current_group = [t]
            else:
                current_group.append(t)
        groups.append(current_group)

        # 3. One highlight per group, centered on the middle of the group.
        highlights: list[DetectedHighlight] = []
        for group in groups:
            center_sec = (group[0] + group[-1]) / 2
            highlights.append(
                DetectedHighlight(
                    center_sec=round(center_sec, 2),
                    duration_sec=self.CLIP_DURATION,
                    kind="kill",
                    confidence=0.9,
                    meta={
                        "source": "ocr",
                        "hit_count": len(group),
                        "first_hit_sec": round(group[0], 2),
                        "last_hit_sec": round(group[-1], 2),
                    },
                )
            )

        highlights.sort(key=lambda h: h.center_sec)
        return highlights