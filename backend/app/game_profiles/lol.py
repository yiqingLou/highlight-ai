"""
League of Legends (LOL) game profile.

Detects kill events by reading the on-screen kill banner with OCR.
For the Chinese (国服) client, the kill banner contains the fixed substring
"击杀了" (e.g. "PlayerA 击杀了 PlayerB!").

Detection strategy:
    For each extracted frame, run OCR and check for the kill keyword.
    Consecutive hits within DEDUP_SECONDS are treated as the SAME kill
    (the banner stays on screen for a few seconds), so they are merged
    into a single highlight.
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

    # Hits closer than this many seconds are treated as the same kill.
    DEDUP_SECONDS = 3.0

    # Clip length around each detected kill.
    CLIP_DURATION = 8.0

    def detect_highlights(
        self,
        frame_paths: list[str],
        fps: float,
    ) -> list[DetectedHighlight]:
        """
        Detect kills by OCR-scanning each frame for the kill keyword.

        Args:
            frame_paths: Ordered list of extracted frame image paths.
            fps: Extraction fps (frames sampled per second), used to convert
                 frame index to a timestamp.

        Returns:
            List of DetectedHighlight (deduplicated), sorted by center_sec.
        """
        if not frame_paths:
            return []

        highlights: list[DetectedHighlight] = []
        last_kill_sec = None  # timestamp of the previous accepted kill

        for frame_index, frame_path in enumerate(frame_paths):
            # Check if any kill keyword appears in this frame.
            hit = any(
                contains_keyword(frame_path, kw)
                for kw in self.KILL_KEYWORDS
            )
            if not hit:
                continue

            center_sec = self.frame_index_to_sec(frame_index, fps)

            # Dedup: skip if too close to the previous accepted kill.
            if last_kill_sec is not None and (center_sec - last_kill_sec) < self.DEDUP_SECONDS:
                continue

            highlights.append(
                DetectedHighlight(
                    center_sec=round(center_sec, 2),
                    duration_sec=self.CLIP_DURATION,
                    kind="kill",
                    confidence=0.9,  # OCR keyword match is fairly reliable
                    meta={"source": "ocr", "frame_index": frame_index},
                )
            )
            last_kill_sec = center_sec

        highlights.sort(key=lambda h: h.center_sec)
        return highlights