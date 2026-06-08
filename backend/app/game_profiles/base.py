"""
Game profile base class and plugin registry.

Every supported game implements a GameProfile subclass that knows how to
detect highlight moments (kills, etc.) from extracted video frames.

The rest of the app only talks to the GameProfile interface and never needs
to know how a specific game detects its highlights.

To add a new game:
    1. Create a new file in this package (e.g. valorant.py)
    2. Subclass GameProfile, set game_id / display_name
    3. Implement detect_highlights()
    4. Register it in the _REGISTRY dict below
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class DetectedHighlight:
    """
    A single highlight moment detected in a video.

    Attributes:
        center_sec: Timestamp (seconds) where the highlight peaks (e.g. kill moment).
        duration_sec: How long the clip around center_sec should be.
        kind: Type of highlight, e.g. "kill", "multi_kill", "clutch".
        confidence: Detector confidence in [0.0, 1.0].
        meta: Optional extra info (frame index, OCR text, etc.).
    """
    center_sec: float
    duration_sec: float
    kind: str
    confidence: float
    meta: dict = field(default_factory=dict)


class GameProfile(ABC):
    """
    Abstract base class for all game profiles (plugins).

    Subclasses MUST set:
        game_id      - short stable identifier, matches Task.game_type (e.g. "naraka")
        display_name - human-readable name (e.g. "Naraka: Bladepoint")

    Subclasses MUST implement:
        detect_highlights() - the game-specific detection logic
    """

    # --- Subclasses must override these two class attributes ---
    game_id: str = ""
    display_name: str = ""

    @abstractmethod
    def detect_highlights(
        self,
        frame_paths: list[str],
        fps: float,
    ) -> list[DetectedHighlight]:
        """
        Detect highlight moments from a list of extracted frames.

        Args:
            frame_paths: Ordered list of frame image paths (from
                         video_processor.extract_frames). Index 0 is the
                         first extracted frame.
            fps: Frames-per-second rate at which frames were extracted
                 (NOT the source video fps). Used to convert frame index
                 to a timestamp. E.g. fps=1 means frame_paths[30] is at 30s.

        Returns:
            List of DetectedHighlight, sorted by center_sec ascending.
            Empty list if nothing detected.
        """
        raise NotImplementedError

    # --- Shared helper available to all subclasses ---
    def frame_index_to_sec(self, frame_index: int, fps: float) -> float:
        """
        Convert a frame index into a timestamp in seconds.

        Args:
            frame_index: Position in the frame_paths list (0-based).
            fps: Extraction fps (frames per second that were sampled).

        Returns:
            Timestamp in seconds. Returns 0.0 if fps is invalid.
        """
        if fps <= 0:
            return 0.0
        return frame_index / fps


# ---------------------------------------------------------------------------
# Plugin registry
# ---------------------------------------------------------------------------
# Maps game_type string -> GameProfile subclass.
# Imports are done lazily inside get_profile() to avoid circular imports
# and to keep this base module dependency-free.

def get_profile(game_type: str) -> GameProfile:
    """
    Return an instance of the GameProfile matching the given game_type.

    Args:
        game_type: Identifier stored on the Task (e.g. "naraka", "lol").

    Returns:
        An instantiated GameProfile subclass.

    Raises:
        ValueError: if no profile is registered for game_type.
    """
    # Lazy import to avoid circular dependencies at module load time
    from .naraka import NarakaProfile

    registry: dict[str, type[GameProfile]] = {
        "naraka": NarakaProfile,
    }

    profile_cls = registry.get(game_type)
    if profile_cls is None:
        available = ", ".join(sorted(registry.keys())) or "(none)"
        raise ValueError(
            f"No game profile registered for '{game_type}'. "
            f"Available: {available}"
        )

    return profile_cls()


def list_supported_games() -> list[dict]:
    """
    Return metadata for all registered game profiles.

    Useful for a future API endpoint / frontend dropdown.

    Returns:
        List of dicts: [{"game_id": ..., "display_name": ...}, ...]
    """
    from .naraka import NarakaProfile

    profiles: list[type[GameProfile]] = [NarakaProfile]
    return [
        {"game_id": p.game_id, "display_name": p.display_name}
        for p in profiles
    ]