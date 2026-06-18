"""
League of Legends (LOL) game profile.

Detects YOUR OWN kills by reading the center-screen first-person kill banner
"你已经击杀了一名敌方英雄" with OCR (the reliable first-person anchor), then
upgrades the kill to a multi-kill tier ONLY when the multi-kill banner in that
frame belongs to YOU.

Why the portrait check (method C): multi-kill banners ("双杀"/"三杀"/"终结") are
broadcast to everyone's screen for ANY player's multi-kill, so the keyword alone
cannot tell whose kill it is. In team fights, another player's multi-kill banner
can appear near your own "你已经击杀" anchor and wrongly upgrade your kill. To fix
this, we check the banner's killer portrait against your HUD champion portrait
(portrait_matcher): only upgrade if they match (the multi-kill is yours).

Your own multi-kill always starts with "你已经击杀" (1st kill) and escalates to
"双杀" (2nd), "三杀" (3rd)... so the anchor is present for your multi-kills.

Detection strategy:
    1. OCR every frame: record "你已经击杀" anchor times, and multi-kill word hits
       together with the frame path (needed for the portrait check).
    2. Keep only the multi-kill hits whose banner portrait matches your HUD
       champion (is_player_multikill) -> these are YOUR multi-kills.
    3. Group consecutive anchors into kill events (gap >= GAP_SECONDS).
    4. Upgrade each event to the highest tier among YOUR multi-kill words within
       UPGRADE_WINDOW seconds of the event. No match -> plain kill.
"""

from .base import GameProfile, DetectedHighlight
from app.services.ocr_detector import contains_keyword
from app.services.portrait_matcher import is_player_multikill


class LolProfile(GameProfile):
    """Game profile for League of Legends (Chinese client)."""

    game_id = "lol"
    display_name = "League of Legends"

    # First-person anchor: ONLY this proves the kill is yours.
    ANCHOR_KEYWORD = "你已经击杀"

    # Multi-kill / special words -> (label, score). NOT first-person; they only
    # upgrade an anchored kill, and only when the banner portrait is YOURS.
    UPGRADE_TIERS = {
        "双杀": ("double_kill", 93),
        "终结": ("shutdown", 95),
        "三杀": ("triple_kill", 96),
        "四杀": ("quadra_kill", 98),
        "五杀": ("penta_kill", 100),
    }

    # Baseline tier for a plain anchored kill (no own multi-kill word nearby).
    BASE_LABEL = "kill"
    BASE_SCORE = 90

    # All words to OCR-scan for (anchor + upgrades).
    KILL_KEYWORDS = [ANCHOR_KEYWORD] + list(UPGRADE_TIERS.keys())

    # A new kill EVENT starts only after this many seconds with no anchor hit.
    GAP_SECONDS = 5.0

    # A multi-kill word counts toward an event if within this many seconds of
    # the event's anchor span (1fps can separate anchor and "双杀"/"三杀" banners).
    UPGRADE_WINDOW = 5.0

    # Clip length around each detected kill.
    CLIP_DURATION = 8.0

    def detect_highlights(
        self,
        frame_paths: list[str],
        fps: float,
    ) -> list[DetectedHighlight]:
        """
        Detect your anchored kills, upgraded by YOUR multi-kills (portrait-checked).

        Args:
            frame_paths: Ordered list of extracted frame image paths.
            fps: Extraction fps, used to convert frame index to seconds.

        Returns:
            List of DetectedHighlight (one per anchored kill event), sorted by time.
        """
        if not frame_paths:
            return []

        # 1. OCR each frame: anchor times, and multi-kill hits with frame path.
        anchor_times: list[float] = []
        upgrade_hits: list[tuple[float, str, str]] = []  # (sec, word, frame_path)
        for frame_index, frame_path in enumerate(frame_paths):
            sec = self.frame_index_to_sec(frame_index, fps)
            if contains_keyword(frame_path, self.ANCHOR_KEYWORD):
                anchor_times.append(sec)
            for word in self.UPGRADE_TIERS:
                if contains_keyword(frame_path, word):
                    upgrade_hits.append((sec, word, frame_path))

        # No anchored kills -> nothing is provably yours.
        if not anchor_times:
            return []

        # 2. Keep only multi-kill hits whose banner portrait matches YOUR HUD
        #    champion (method C). This drops other players' broadcast multi-kills.
        player_upgrade_hits: list[tuple[float, str]] = [
            (sec, word)
            for (sec, word, frame_path) in upgrade_hits
            if is_player_multikill(frame_path)
        ]

        # 3. Group consecutive anchors into kill events.
        events: list[list[float]] = []
        current: list[float] = [anchor_times[0]]
        for t in anchor_times[1:]:
            if t - current[-1] >= self.GAP_SECONDS:
                events.append(current)
                current = [t]
            else:
                current.append(t)
        events.append(current)

        # 4. Upgrade each event by YOUR multi-kill words within UPGRADE_WINDOW.
        highlights: list[DetectedHighlight] = []
        for event in events:
            first_anchor = event[0]
            last_anchor = event[-1]
            center_sec = (first_anchor + last_anchor) / 2

            nearby_words: set[str] = set()
            for sec, word in player_upgrade_hits:
                if (first_anchor - self.UPGRADE_WINDOW) <= sec <= (last_anchor + self.UPGRADE_WINDOW):
                    nearby_words.add(word)

            if nearby_words:
                best_word = max(nearby_words, key=lambda w: self.UPGRADE_TIERS[w][1])
                label, score = self.UPGRADE_TIERS[best_word]
            else:
                label, score = self.BASE_LABEL, self.BASE_SCORE

            highlights.append(
                DetectedHighlight(
                    center_sec=round(center_sec, 2),
                    duration_sec=self.CLIP_DURATION,
                    kind=label,
                    confidence=round(score / 100, 2),
                    meta={
                        "source": "ocr+portrait",
                        "tier": label,
                        "score": score,
                        "anchor_hits": len(event),
                        "own_upgrade_words": sorted(nearby_words),
                        "first_anchor_sec": round(first_anchor, 2),
                        "last_anchor_sec": round(last_anchor, 2),
                    },
                )
            )

        highlights.sort(key=lambda h: h.center_sec)
        return highlights