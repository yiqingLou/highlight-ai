"""
League of Legends (LOL) game profile.

Detects kill events by reading the on-screen kill banner with OCR.
For the Chinese (国服) client, the kill banner contains the fixed substring
"击杀了" (e.g. "PlayerA 击杀了 PlayerB!").

Detection strategy:
    Run OCR on every frame and mark which frames contain the kill keyword.
    The banner stays on screen for several seconds, so many consecutive
    frames hit. We GROUP consecutive hits into one kill event: a new event
    only starts after a gap of >= GAP_SECONDS with no hits. Each group
    becomes a single highlight centered on the group's middle.
"""

from .base import GameProfile, DetectedHighlight
from app.services.ocr_detector import contains_keyword


class LolProfile(GameProfile):
    """Game profile for League of Legends (Chinese client)."""

    game_id = "lol"
    display_name = "League of Legends"

    # Kill banner keyword(s). Add other-server variants here later, e.g.
    # "적을 처치했습니다" (KR), "You have slain" / "killed" (EN).
    KILL_KEYWORDS = ["击杀了", "你已经击杀了"]

    # A new kill event starts only after this many seconds with no hits.
    # The banner persists for several seconds, so consecutive hits within
    # this gap are treated as ONE kill event (avoids splitting one banner
    # into many highlights).
    GAP_SECONDS = 5.0

    # Clip length around each detected kill.
    CLIP_DURATION = 8.0

    def detect_highlights(
        self,
        frame_paths: list[str],
        fps: float,
    ) -> list[DetectedHighlight]:
        """
        Detect kills by OCR-scanning frames and grouping consecutive hits.

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
                    confidence=0.9,  # OCR keyword match is fairly reliable
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