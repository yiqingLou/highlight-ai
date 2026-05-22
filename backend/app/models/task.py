"""
Task model - the 'tasks' table.
Stores every video the user uploads for processing.
"""

from sqlalchemy import Column, Integer, String, Float, DateTime, Text
from sqlalchemy.sql import func

from app.database import Base


class Task(Base):
    __tablename__ = "tasks"

    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True)

    # File info
    file_path = Column(Text, nullable=False)
    file_name = Column(String, nullable=False)
    file_size = Column(Integer)

    # Video metadata
    duration_sec = Column(Float)
    width = Column(Integer)
    height = Column(Integer)
    fps = Column(Float)

    # Game type
    game_type = Column(String)

    # Processing status
    status = Column(String, nullable=False, default="pending")
    progress = Column(Integer, default=0)
    error_message = Column(Text)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    completed_at = Column(DateTime(timezone=True))

    def __repr__(self):
        return f"<Task id={self.id} file_name='{self.file_name}' status='{self.status}'>"