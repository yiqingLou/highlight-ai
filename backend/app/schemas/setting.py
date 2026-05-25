"""
Pydantic schemas for Settings API responses.
"""

from pydantic import BaseModel


class SettingsResponse(BaseModel):
    """All user settings as a dict (key -> value)."""
    settings: dict[str, str]