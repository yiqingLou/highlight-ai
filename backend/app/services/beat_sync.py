"""Beat detection for BGM alignment.

Uses librosa to find onset peaks (the punchy accents in a track) so the
montage can shift the BGM to land a perceptible hit exactly on the first kill.
"""


def detect_strong_beats(bgm_path: str) -> list[float]:
    """Return strong-beat times (seconds) of an audio file, every 4th beat."""
    import librosa  # imported lazily: heavy dependency

    y, sr = librosa.load(bgm_path)
    _tempo, beats = librosa.beat.beat_track(y=y, sr=sr)
    times = librosa.frames_to_time(beats, sr=sr)
    return [float(t) for t in times[::4]]


def detect_hits(bgm_path: str, top_n: int = 30, min_gap: float = 1.0) -> list[float]:
    """Return the strongest onset moments ("hits") in the track, ascending.

    These are the punchy accents (drum slams, section entries) — far more
    recognizable than regular bar downbeats, so landing a kill on one of
    these actually FEELS beat-synced.
    """
    import librosa
    import numpy as np

    y, sr = librosa.load(bgm_path)
    onset = librosa.onset.onset_strength(y=y, sr=sr)
    times = librosa.times_like(onset, sr=sr)
    idx = np.argsort(onset)[::-1][:top_n]
    peaks = sorted(float(times[i]) for i in idx)
    merged: list[float] = []
    for p in peaks:
        if not merged or p - merged[-1] > min_gap:
            merged.append(p)
    return merged


def bgm_trim_for_kill(kill_time_sec: float, beat_times: list[float]) -> float:
    """How much to trim off the BGM head so a strong beat hits kill_time_sec.

    Picks the first strong beat at/after kill_time_sec; trimming the BGM head
    by (beat - kill_time) makes that beat play exactly at the kill moment.
    Returns 0.0 if no suitable beat exists.
    """
    for beat in beat_times:
        if beat >= kill_time_sec:
            return round(beat - kill_time_sec, 3)
    return 0.0
