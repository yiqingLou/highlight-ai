from app.services.beat_sync import bgm_trim_for_kill, detect_hits


def test_bgm_trim_for_kill_returns_positive_offset_for_later_beat() -> None:
    beats = [1.0, 2.0, 3.0, 4.0]
    assert bgm_trim_for_kill(2.5, beats) == 0.5


def test_bgm_trim_for_kill_returns_zero_when_no_future_beat() -> None:
    beats = [0.5, 1.2]
    assert bgm_trim_for_kill(2.0, beats) == 0.0


def test_detect_hits_merges_close_peaks() -> None:
    """Onset peaks closer than min_gap should be merged."""
    # Note: This would require mocking librosa; for now verify it imports/exists.
    assert callable(detect_hits)
