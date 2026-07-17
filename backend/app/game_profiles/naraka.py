"""
Naraka: Bladepoint game profile.

Real detection in two stages:
  1. Per-frame YOLO finds the "weapon scratch" kill icon. Adjacent frames
     where the scratch persists are merged into a single kill event (one
     real kill is not counted multiple times).
  2. Kill events that happen close together in time are grouped into a
     multi-kill highlight (double / triple / quadra / penta). A lone kill
     stays a single "kill".

The kind on each DetectedHighlight (kill / double_kill / ...) is what the
task pipeline maps to a score, so multi-kills outrank single kills.

Model: ml/models/naraka_kill.pt  (single class "kill")
"""

from .base import GameProfile, DetectedHighlight
from app.paths import MODELS_DIR

# --- Detection tuning -----------------------------------------------------
# Minimum confidence for a YOLO detection to count as a real kill. At 0.55,
# borderline false positives such as a held weapon misread at ~0.51 are
# filtered while real kills remain comfortably above the threshold.
CONF_THRESHOLD = 0.55

# Frames sampled at fps; scratch detections closer than this many seconds are
# the SAME kill (the icon persists across 2-3 neighbouring frames at 1 fps).
SAME_KILL_GAP_SEC = 2.0

# Two separate kills within this many seconds belong to the same multi-kill
# streak. Naraka is melee-paced, so the streak window is wider than a MOBA's.
# Tune this single number if streaks are being split or over-merged.
STREAK_GAP_SEC = 12.0

# Padding (seconds) added before the first kill and after the last kill of a
# streak, so the clip has lead-in and follow-through.
CLIP_PAD_SEC = 7.0

# Single-kill timing: a long buildup before the kill, then a quick cut away.
SINGLE_PRE_SEC = 8.5
SINGLE_POST_SEC = 1.3

# Minimum clip length for a single kill (seconds), centred on the kill.
SINGLE_KILL_DURATION_SEC = 8.0

# Map a streak length (number of kills) to a highlight kind. 5 or more is a
# penta. These kind strings match the scoring table in the task pipeline.
_STREAK_KIND = {
    1: "kill",
    2: "double_kill",
    3: "triple_kill",
    4: "quadra_kill",
}
_PENTA_KIND = "penta_kill"  # 5 or more

# Path to the trained weights, relative to the project root.
# This file lives at backend/app/game_profiles/naraka.py, so go up three
# levels to reach the project root, then into ml/models.
_MODEL_PATH = MODELS_DIR / "naraka_kill.pt"


class NarakaProfile(GameProfile):
    """Game profile for Naraka: Bladepoint (real YOLO detection)."""

    game_id = "naraka"
    display_name = "Naraka: Bladepoint"

    # Class-level model cache so the weights load only once per process.
    _model = None

    @classmethod
    def _get_model(cls):
        """Lazily load and cache the YOLO model."""
        if cls._model is None:
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
        Detect kills with YOLO, then group nearby kills into multi-kills.

        Args:
            frame_paths: Ordered list of extracted frame image paths.
            fps: Extraction fps (frames per second sampled).

        Returns:
            List of DetectedHighlight, sorted by center_sec ascending.
        """
        if not frame_paths:
            return []

        # --- Stage 1: per-frame inference -> single kill events ---
        kill_events = self._detect_kill_events(frame_paths, fps)
        if not kill_events:
            return []

        # --- Stage 2: group nearby kills into streaks (multi-kills) ---
        return self._group_into_streaks(kill_events)

    def _detect_kill_events(
        self,
        frame_paths: list[str],
        fps: float,
    ) -> list[dict]:
        """
        Run YOLO on every frame and merge adjacent scratch frames into single
        kill events.

        Returns:
            List of dicts {center_sec, conf}, one per distinct kill, ascending.
        """
        model = self._get_model()

        # stream=True keeps memory flat regardless of video length.
        results = model.predict(
            source=frame_paths,
            conf=CONF_THRESHOLD,
            verbose=False,
            stream=True,
        )

        # Frames (by index) that contain a scratch above threshold.
        kill_frames: list[tuple[int, float]] = []
        for frame_index, result in enumerate(results):
            boxes = result.boxes
            if boxes is None or len(boxes) == 0:
                continue
            best_conf = float(boxes.conf.max())
            kill_frames.append((frame_index, best_conf))

        if not kill_frames:
            return []

        # Merge frames that are within SAME_KILL_GAP_SEC into one kill event.
        same_kill_gap_frames = max(1, int(round(SAME_KILL_GAP_SEC * fps)))

        events: list[dict] = []
        group_best_conf = kill_frames[0][1]
        group_best_index = kill_frames[0][0]
        prev_index = kill_frames[0][0]

        def flush():
            events.append({
                "center_sec": self.frame_index_to_sec(group_best_index, fps),
                "conf": group_best_conf,
            })

        for frame_index, conf in kill_frames[1:]:
            if frame_index - prev_index <= same_kill_gap_frames:
                if conf > group_best_conf:
                    group_best_conf = conf
                    group_best_index = frame_index
                prev_index = frame_index
            else:
                flush()
                group_best_conf = conf
                group_best_index = frame_index
                prev_index = frame_index
        flush()

        return events

    def _group_into_streaks(
        self,
        kill_events: list[dict],
    ) -> list[DetectedHighlight]:
        """
        Group kill events that occur within STREAK_GAP_SEC of each other into
        a single multi-kill highlight.

        Args:
            kill_events: list of {center_sec, conf}, ascending by center_sec.

        Returns:
            List of DetectedHighlight, ascending by center_sec.
        """
        highlights: list[DetectedHighlight] = []

        # Start the first streak with the first kill.
        streak: list[dict] = [kill_events[0]]

        def flush_streak():
            """Turn the current streak of kills into one DetectedHighlight."""
            n_kills = len(streak)
            first_sec = streak[0]["center_sec"]
            last_sec = streak[-1]["center_sec"]

            # Kind by streak length (5+ = penta).
            kind = _STREAK_KIND.get(n_kills, _PENTA_KIND)

            # Best detection confidence across the streak (for reference only).
            best_conf = max(k["conf"] for k in streak)

            if n_kills == 1:
                # Single kill: 5s buildup before the kill, then 1.5s after.
                start_sec = max(0.0, first_sec - SINGLE_PRE_SEC)
                end_sec = first_sec + SINGLE_POST_SEC
                center_sec = (start_sec + end_sec) / 2
                duration_sec = end_sec - start_sec
            else:
                # Multi-kill: clip spans first..last kill plus padding.
                start_sec = max(0.0, first_sec - CLIP_PAD_SEC)
                end_sec = last_sec + CLIP_PAD_SEC
                center_sec = (start_sec + end_sec) / 2
                duration_sec = end_sec - start_sec

            highlights.append(
                DetectedHighlight(
                    center_sec=round(center_sec, 2),
                    duration_sec=round(duration_sec, 2),
                    kind=kind,
                    confidence=round(best_conf, 3),
                    meta={
                        "source": "yolo",
                        "kill_count": n_kills,
                        "first_kill_sec": round(first_sec, 2),
                        "last_kill_sec": round(last_sec, 2),
                    },
                )
            )

        for event in kill_events[1:]:
            if event["center_sec"] - streak[-1]["center_sec"] <= STREAK_GAP_SEC:
                # Within the streak window: extend the current streak.
                streak.append(event)
            else:
                # Gap too large: close this streak, start a new one.
                flush_streak()
                streak = [event]
        flush_streak()

        highlights.sort(key=lambda h: h.center_sec)
        return highlights