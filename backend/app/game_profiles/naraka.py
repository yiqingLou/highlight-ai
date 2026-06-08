"""
Naraka: Bladepoint game profile.

MVP stage: detect_highlights() returns FAKE hardcoded data so we can wire up
the full pipeline (extract frames -> detect -> store highlights -> query API)
before investing in real detection.

Week 4 later / Week 5: replace the fake logic with real OCR (read the
"击败" kill banner) or YOLO-based visual detection.
"""

from .base import GameProfile, DetectedHighlight


class NarakaProfile(GameProfile):
    """Game profile for Naraka: Bladepoint."""

    game_id = "naraka"
    display_name = "Naraka: Bladepoint"

    def detect_highlights(
        self,
        frame_paths: list[str],
        fps: float,
    ) -> list[DetectedHighlight]:
        """
        MVP placeholder: return fake highlights instead of real detection.

        This lets us validate the end-to-end pipeline. The fake highlights are
        spaced through the video based on how many frames exist, so the output
        scales with video length instead of being fixed timestamps.

        Args:
            frame_paths: Ordered list of extracted frame image paths.
            fps: Extraction fps (frames per second sampled).

        Returns:
            List of DetectedHighlight, sorted by center_sec ascending.
        """
        # If no frames were extracted, there is nothing to detect.
        if not frame_paths:
            return []

        total_frames = len(frame_paths)

        # Fake strategy: place a highlight at 25%, 50%, and 75% of the video.
        # This is NOT real detection - just enough to exercise the pipeline.
        fake_positions = [0.25, 0.50, 0.75]

        highlights: list[DetectedHighlight] = []
        for pos in fake_positions:
            frame_index = int(total_frames * pos)
            center_sec = self.frame_index_to_sec(frame_index, fps)

            highlights.append(
                DetectedHighlight(
                    center_sec=round(center_sec, 2),
                    duration_sec=8.0,          # 8s clip around the kill
                    kind="kill",
                    confidence=0.5,            # fake/low confidence on purpose
                    meta={"source": "fake_mvp", "frame_index": frame_index},
                )
            )

        # Already in ascending order, but sort to honor the interface contract.
        highlights.sort(key=lambda h: h.center_sec)
        return highlights