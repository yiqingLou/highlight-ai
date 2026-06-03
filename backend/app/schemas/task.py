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
    """
    Response for GET /api/tasks/.

    Fields:
        tasks: This page's tasks (limited by ?limit=)
        total: Number in this response (len of tasks)
        total_count: Total in database matching the filter (across all pages)
        skip: How many records were skipped
        limit: Page size used
    """
    tasks: list[TaskResponse]
    total: int
    total_count: int
    skip: int
    limit: int


class TaskCreate(BaseModel):
    """
    Schema for creating a new task (POST /api/tasks request body).
    """
    file_path: str
    file_name: str
    file_size: Optional[int] = None
    duration_sec: Optional[float] = None
    width: Optional[int] = None
    height: Optional[int] = None
    fps: Optional[float] = None
    game_type: Optional[str] = None