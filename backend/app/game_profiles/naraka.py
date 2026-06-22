"""
Naraka: Bladepoint game profile.

Real detection: uses a trained YOLO model to find the "weapon scratch" kill
icon in each frame. Frames where the scratch is detected (confidence above
threshold) are treated as the player's own kills. Adjacent kill frames are
merged into a single highlight so one kill is not reported multiple times.

Model: ml/models/naraka_kill.pt  (single class "kill")
"""

from pathlib import Path

from .base import GameProfile, DetectedHighlight

# --- Detection tuning -----------------------------------------------------
# Minimum confidence for a detection to count as a real kill. At 0.5 the
# low-confidence UI/buff-icon false positives are filtered out (verified on
# the scan set: false positives drop to zero at this threshold).
CONF_THRESHOLD = 0.5

# Frames sampled at fps; kills closer than this many seconds are treated as
# the same kill event and merged. At 1 fps, a value of 2.0 merges scratch
# detections that persist across 2-3 neighbouring frames.
MERGE_GAP_SEC = 2.0

# Clip length (seconds) centred on each detected kill.
CLIP_DURATION_SEC = 8.0

# Path to the trained weights, relative to the project root.
# This file lives at backend/app/game_profiles/naraka.py, so go up three
# levels to reach the project root, then into ml/models.
_MODEL_PATH = (
    Path(__file__).resolve().parents[3] / "ml" / "models" / "naraka_kill.pt"
)


class NarakaProfile(GameProfile):
    """Game profile for Naraka: Bladepoint (real YOLO detection)."""

    game_id = "naraka"
    display_name = "Naraka: Bladepoint"

    # Class-level model cache so the weights load only once per process,
    # not on every request or every frame.
    _model = None

    @classmethod
    def _get_model(cls):
        """Lazily load and cache the YOLO model."""
        if cls._model is None:
            # Imported here so the rest of the app does not depend on
            # ultralytics unless Naraka detection is actually used.
            from ultralytics import YOLO

            if not _MODEL_PATH.exists():
                raise FileNotFoundError(
                    f"Naraka model weights not found at {_MODEL_PATH}. "
                    f"Train the model or copy best.pt to ml/models/naraka_kill.pt."
                )
            cls._model = YOLO(str(_MODEL_PATH))
        return cls._model

    def detect_highlights(
        self,
        frame_paths: list[str],
        fps: float,
    ) -> list[DetectedHighlight]:
        """
        Run YOLO on each frame, then merge adjacent kill frames into events.

        Args:
            frame_paths: Ordered list of extracted frame image paths.
            fps: Extraction fps (frames per second sampled).

        Returns:
            List of DetectedHighlight, sorted by center_sec ascending.
        """
        if not frame_paths:
            return []

        model = self._get_model()

        # stream=True returns a generator: each frame's result is processed and
        # released instead of accumulating all of them in RAM. This keeps memory
        # flat regardless of video length.
        results = model.predict(
            source=frame_paths,
            conf=CONF_THRESHOLD,
            verbose=False,
            stream=True,
        )

        # Collect (frame_index, best_confidence) for frames that have at least
        # one detection above the confidence threshold.
        kill_frames: list[tuple[int, float]] = []
        for frame_index, result in enumerate(results):
            boxes = result.boxes
            if boxes is None or len(boxes) == 0:
                continue
            # Highest-confidence detection in this frame.
            best_conf = float(boxes.conf.max())
            kill_frames.append((frame_index, best_conf))

        if not kill_frames:
            return []

        # Merge adjacent kill frames into single kill events. Two detections
        # within MERGE_GAP_SEC of each other belong to the same kill.
        merge_gap_frames = max(1, int(round(MERGE_GAP_SEC * fps)))

        highlights: list[DetectedHighlight] = []
        group_start = kill_frames[0][0]
        prev_index = kill_frames[0][0]
        group_best_conf = kill_frames[0][1]
        group_best_index = kill_frames[0][0]

        def flush_group():
            """Turn the current group into one DetectedHighlight."""
            center_sec = self.frame_index_to_sec(group_best_index, fps)
            highlights.append(
                DetectedHighlight(
                    center_sec=round(center_sec, 2),
                    duration_sec=CLIP_DURATION_SEC,
                    kind="kill",
                    confidence=round(group_best_conf, 3),
                    meta={
                        "source": "yolo",
                        "frame_index": group_best_index,
                        "group_start": group_start,
                        "group_end": prev_index,
                    },
                )
            )

        for frame_index, conf in kill_frames[1:]:
            if frame_index - prev_index <= merge_gap_frames:
                # Same kill event: extend the current group.
                if conf > group_best_conf:
                    group_best_conf = conf
                    group_best_index = frame_index
                prev_index = frame_index
            else:
                # Gap too large: close the current group, start a new one.
                flush_group()
                group_start = frame_index
                prev_index = frame_index
                group_best_conf = conf
                group_best_index = frame_index

        # Flush the final group.
        flush_group()

        highlights.sort(key=lambda h: h.center_sec)
        return highlights