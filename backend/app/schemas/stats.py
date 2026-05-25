"""
Pydantic schemas for Stats API responses.
"""

from pydantic import BaseModel


class TotalsBreakdown(BaseModel):
    """Counts of each main entity."""
    tasks: int
    highlights: int
    clips: int
    bgm_tracks: int


class TopHighlight(BaseModel):
    """A compact highlight for the top-3 list in stats."""
    id: int
    label: str | None
    score: int | None


class StatsResponse(BaseModel):
    """Aggregated project statistics."""
    totals: TotalsBreakdown
    tasks_by_status: dict[str, int]
    total_duration_sec: float
    total_duration_human: str
    avg_highlight_score: float
    top_highlights: list[TopHighlight]