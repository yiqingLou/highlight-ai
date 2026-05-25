"""
Pydantic schemas for BGM API responses.
"""

from pydantic import BaseModel
from typing import Optional


class BgmResponse(BaseModel):
    """A single BGM track."""
    id: int
    name: str
    style: Optional[str] = None
    duration_sec: Optional[float] = None

    class Config:
        from_attributes = True


class BgmListResponse(BaseModel):
    """Wrapper for /api/bgm endpoint."""
    bgm: list[BgmResponse]
    total: int