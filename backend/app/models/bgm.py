"""
Bgm model - the 'bgm' table.
Pre-loaded BGM library (static data).
"""

from sqlalchemy import Column, Integer, Float, String, Text

from app.database import Base


class Bgm(Base):
    __tablename__ = "bgm"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    file_path = Column(Text, nullable=False)
    style = Column(String)
    duration_sec = Column(Float)
    license = Column(String)
    sort_order = Column(Integer)

    def __repr__(self):
        return f"<Bgm id={self.id} name='{self.name}' style='{self.style}'>"