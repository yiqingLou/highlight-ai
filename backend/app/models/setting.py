"""
Setting model - the 'settings' table.
Key-value store for user preferences.
"""

from sqlalchemy import Column, String, DateTime
from sqlalchemy.sql import func

from app.database import Base


class Setting(Base):
    __tablename__ = "settings"

    key = Column(String, primary_key=True)
    value = Column(String)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    def __repr__(self):
        return f"<Setting key='{self.key}' value='{self.value}'>"