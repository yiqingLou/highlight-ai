"""
Clip model - the 'clips' table.
Exported short videos (one task can have multiple clips).
"""

from sqlalchemy import Column, Integer, Float, String, Boolean, DateTime, Text, ForeignKey
from sqlalchemy.sql import func

from app.database import Base


class Clip(Base):
    __tablename__ = "clips"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(Integer, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False)

    # Output file
    output_path = Column(Text, nullable=False)
    file_size = Column(Integer)
    duration_sec = Column(Float)

    # Settings
    aspect_ratio = Column(String)
    resolution = Column(String)

    # BGM
    bgm_id = Column(Integer, ForeignKey("bgm.id", ondelete="SET NULL"))
    bgm_volume = Column(Float, default=0.4)
    voice_volume = Column(Float, default=0.8)

    # Subtitle
    has_subtitle = Column(Boolean, default=True)

    # Which highlights used (JSON array as string)
    highlight_ids = Column(Text)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self):
        return f"<Clip id={self.id} task_id={self.task_id} aspect_ratio='{self.aspect_ratio}'>"