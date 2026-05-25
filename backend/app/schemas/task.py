"""
Pydantic schemas for Task API responses.
"""

from pydantic import BaseModel
from typing import Optional


class TaskResponse(BaseModel):
    """Compact task for list views (used by GET /api/tasks)."""
    id: int
    file_name: str
    duration_sec: Optional[float] = None
    status: str
    progress: int = 0
    game_type: Optional[str] = None

    class Config:
        from_attributes = True


class TaskDetailResponse(BaseModel):
    """Detailed task (used by GET /api/tasks/{id})."""
    id: int
    file_name: str
    file_path: str
    file_size: Optional[int] = None
    duration_sec: Optional[float] = None
    width: Optional[int] = None
    height: Optional[int] = None
    fps: Optional[float] = None
    game_type: Optional[str] = None
    status: str
    progress: int = 0
    error_message: Optional[str] = None
    # Computed fields
    highlight_count: int
    highlight_ids: list[int]

    class Config:
        from_attributes = True


class TaskListResponse(BaseModel):
    """Wrapper for list endpoint."""
    tasks: list[TaskResponse]
    total: int