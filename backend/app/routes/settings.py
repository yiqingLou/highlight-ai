"""
Settings routes - /api/settings
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Setting
from app.schemas.setting import SettingsResponse

router = APIRouter()


@router.get("/", response_model=SettingsResponse)
def get_settings(db: Session = Depends(get_db)):
    """Return all user settings as a key-value dict."""
    settings = db.query(Setting).all()
    return {
        "settings": {s.key: s.value for s in settings}
    }