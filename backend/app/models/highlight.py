"""
Highlight model - the 'highlights' table.
AI-detected highlight segments for each task.
"""

from sqlalchemy import Column, Integer, Float, String, Boolean, DateTime, Text, ForeignKey
from sqlalchemy.sql import func

from app.database import Base


class Highlight(Base):
    __tablename__ = "highlights"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(Integer, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False)

    # Time range
    start_sec = Column(Float, nullable=False)
    end_sec = Column(Float, nullable=False)

    # AI scores (0-100)
    score = Column(Integer)
    score_ocr = Column(Integer)
    score_audio = Column(Integer)
    score_visual = Column(Integer)

    # AI metadata
    label = Column(String)
    reason = Column(Text)
    thumbnail_path = Column(Text)

    # User interaction
    is_selected = Column(Boolean, default=True)
    user_modified = Column(Boolean, default=False)

    sort_order = Column(Integer)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self):
        return f"<Highlight id={self.id} label='{self.label}' score={self.score}>"