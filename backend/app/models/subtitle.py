"""
Subtitle model - the 'subtitles' table.
Per-line subtitles for each clip.
"""

from sqlalchemy import Column, Integer, Float, String, Text, ForeignKey

from app.database import Base


class Subtitle(Base):
    __tablename__ = "subtitles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    clip_id = Column(Integer, ForeignKey("clips.id", ondelete="CASCADE"), nullable=False)

    start_sec = Column(Float, nullable=False)
    end_sec = Column(Float, nullable=False)
    text = Column(Text, nullable=False)
    language = Column(String, default="zh")

    def __repr__(self):
        return f"<Subtitle id={self.id} clip_id={self.clip_id}>"