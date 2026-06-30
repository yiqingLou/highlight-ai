"""
ViralScore - highlight excitement scoring.

Fuses multiple signals into a single 0-100 "how exciting is this clip" score,
used to decide which highlights make the montage and in what order.

MVP signals (two, weighted):
  - Streak level (single/double/triple/...): the dominant signal.
  - Real kill span (last_kill - first_kill): in Naraka a kill is a drawn-out
duel, so a longer real fight is more exciting. Padding added at clip time
is deliberately excluded.

Confidence is not yet a signal (not stored on highlights). When conf is added
to detection meta later, it can join here without changing callers.
"""

import ast

# Streak-level sub-score (0-100). Single kills start at 60 so a strong single
# can still clear the montage threshold; multi-kills rank progressively higher.
STREAK_SCORE = {
    "kill": 60,
    "double_kill": 78,
    "triple_kill": 88,
    "quadra_kill": 95,
    "penta_kill": 100,
}

# Real kill span (seconds) that maps to a full duration sub-score.
DURATION_FULL_SEC = 15.0
# Base duration sub-score for a single kill (span == 0).
DURATION_BASE = 40.0

# Signal weights (must sum to 1.0). Streak level is the dominant "hard" signal
# (two kills always beats one), so it carries most of the weight; duration
# only differentiates within the same streak level.
W_STREAK = 0.80
W_DURATION = 0.20

def _parse_meta(reason: str) -> dict:
    """Safely parse a highlight.reason dict-repr string into a dict."""
    if not reason:
        return {}
    try:
        meta = ast.literal_eval(reason)
        return meta if isinstance(meta, dict) else {}
    except (ValueError, SyntaxError):
        return {}


def _streak_subscore(label: str) -> float:
    """Sub-score from the streak level. Unknown labels fall back to single."""
    return float(STREAK_SCORE.get(label, STREAK_SCORE["kill"]))


def _duration_subscore(first_kill_sec: float, last_kill_sec: float) -> float:
    """
    Sub-score from the real kill span (last - first kill).

    A single kill (span 0) gets DURATION_BASE; longer real fights scale up
    linearly to 100 at DURATION_FULL_SEC seconds and cap there.
    """
    span = max(0.0, last_kill_sec - first_kill_sec)
    if span <= 0:
        return DURATION_BASE
    scaled = (span / DURATION_FULL_SEC) * 100.0
    return min(100.0, scaled)


def compute_viral_score(label: str, reason: str) -> int:
    """
    Compute a 0-100 ViralScore for a highlight.

    Args:
        label: Highlight kind ("kill", "double_kill", ...).
        reason: highlight.reason dict-repr, expected to carry
                'first_kill_sec' and 'last_kill_sec'.

    Returns:
        Integer 0-100 excitement score.
    """
    meta = _parse_meta(reason)
    first_kill = float(meta.get("first_kill_sec", 0.0))
    last_kill = float(meta.get("last_kill_sec", first_kill))

    streak = _streak_subscore(label)
    duration = _duration_subscore(first_kill, last_kill)

    score = streak * W_STREAK + duration * W_DURATION
    return round(score)


def compute_viral_score_from_meta(label: str, meta: dict) -> int:
    """
    Same as compute_viral_score but takes the meta dict directly (detection
    stage has the dict; query stage has the reason string).

    Args:
        label: Highlight kind ("kill", "double_kill", ...).
        meta: Detection meta, expected to carry 'first_kill_sec' and
              'last_kill_sec'.

    Returns:
        Integer 0-100 excitement score.
    """
    first_kill = float(meta.get("first_kill_sec", 0.0))
    last_kill = float(meta.get("last_kill_sec", first_kill))

    streak = _streak_subscore(label)
    duration = _duration_subscore(first_kill, last_kill)

    score = streak * W_STREAK + duration * W_DURATION
    return round(score)
