"""
League of Legends (LOL) game profile.

Detects YOUR OWN kills by reading the center-screen first-person kill banner
"你已经击杀了一名敌方英雄" with OCR. This banner appears ONLY when YOU get a
kill (it is first-person), making it a reliable anchor.

Multi-kill banners ("双杀"/"三杀"/"四杀"/"五杀"/"终结") are NOT first-person:
LoL broadcasts them to everyone's screen when ANY player gets a multi-kill, so
the word alone cannot tell whose kill it is. Therefore multi-kill words only
UPGRADE a kill that is already anchored by a nearby "你已经击杀". A multi-kill
word with no anchor nearby belongs to another player and is ignored.

Your own multi-kill always starts with "你已经击杀" (1st kill) and then escalates
to "双杀" (2nd), "三杀" (3rd), etc., so the anchor is present for your multi-kills.

Detection strategy:
    1. OCR every frame, recording which keyword(s) hit and when.
    2. Group consecutive "你已经击杀" anchors into kill events (gap >= GAP_SECONDS).
    3. For each event, look within UPGRADE_WINDOW seconds of the event for
       multi-kill words and upgrade the label/score to the highest tier found.
    4. Multi-kill words with no anchor nearby are discarded (other players').
"""

from .base import GameProfile, DetectedHighlight
from app.services.ocr_detector import contains_keyword


class LolProfile(GameProfile):
    """Game profile for League of Legends (Chinese client)."""

    game_id = "lol"
    display_name = "League of Legends"

    # First-person anchor: ONLY this proves the kill is yours.
    ANCHOR_KEYWORD = "你已经击杀"

    # Multi-kill / special words -> (label, score). NOT first-person, so they
    # only upgrade an anchored kill; they never create a highlight on their own.
    UPGRADE_TIERS = {
        "双杀": ("double_kill", 93),
        "终结": ("shutdown", 95),
        "三杀": ("triple_kill", 96),
        "四杀": ("quadra_kill", 98),
        "五杀": ("penta_kill", 100),
    }

    # Baseline tier for a plain anchored kill (no multi-kill word nearby).
    BASE_LABEL = "kill"
    BASE_SCORE = 90

    # All words to OCR-scan for (anchor + upgrades).
    KILL_KEYWORDS = [ANCHOR_KEYWORD] + list(UPGRADE_TIERS.keys())

    # A new kill EVENT starts only after this many seconds with no anchor hit.
    GAP_SECONDS = 5.0

    # A multi-kill word counts toward an event if it occurs within this many
    # seconds of the event's anchor time span. (1fps sampling can put the
    # anchor and the "双杀"/"三杀" banners a few seconds apart.)
    UPGRADE_WINDOW = 5.0

    # Clip length around each detected kill.
    CLIP_DURATION = 8.0

    def detect_highlights(
        self,
        frame_paths: list[str],
        fps: float,
    ) -> list[DetectedHighlight]:
        """
        Detect your kills (anchored) with multi-kill upgrade.

        Args:
            frame_paths: Ordered list of extracted frame image paths.
            fps: Extraction fps, used to convert frame index to seconds.

        Returns:
            List of DetectedHighlight (one per anchored kill event), sorted by time.
        """
        if not frame_paths:
            return []

        # 1. OCR each frame: record (sec, set of keywords found).
        anchor_times: list[float] = []
        upgrade_hits: list[tuple[float, str]] = []  # (sec, upgrade_word)
        for frame_index, frame_path in enumerate(frame_paths):
            sec = self.frame_index_to_sec(frame_index, fps)
            if contains_keyword(frame_path, self.ANCHOR_KEYWORD):
                anchor_times.append(sec)
            for word in self.UPGRADE_TIERS:
                if contains_keyword(frame_path, word):
                    upgrade_hits.append((sec, word))

        # No anchored kills -> nothing is provably yours.
        if not anchor_times:
            return []

        # 2. Group consecutive anchors into kill events.
        events: list[list[float]] = []
        current: list[float] = [anchor_times[0]]
        for t in anchor_times[1:]:
            if t - current[-1] >= self.GAP_SECONDS:
                events.append(current)
                current = [t]
            else:
                current.append(t)
        events.append(current)

        # 3. For each event, find multi-kill words within UPGRADE_WINDOW of its
        #    anchor span, and upgrade to the highest tier found.
        highlights: list[DetectedHighlight] = []
        for event in events:
            first_anchor = event[0]
            last_anchor = event[-1]
            center_sec = (first_anchor + last_anchor) / 2

            # Collect upgrade words near this event's anchor span.
            nearby_words: set[str] = set()
            for sec, word in upgrade_hits:
                if (first_anchor - self.UPGRADE_WINDOW) <= sec <= (last_anchor + self.UPGRADE_WINDOW):
                    nearby_words.add(word)

            # Pick the highest-scoring tier (or baseline if no upgrade nearby).
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
                        "source": "ocr",
                        "tier": label,
                        "score": score,
                        "anchor_hits": len(event),
                        "upgrade_words": sorted(nearby_words),
                        "first_anchor_sec": round(first_anchor, 2),
                        "last_anchor_sec": round(last_anchor, 2),
                    },
                )
            )

        highlights.sort(key=lambda h: h.center_sec)
        return highlights