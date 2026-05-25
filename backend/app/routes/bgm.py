"""
BGM routes - /api/bgm
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Bgm
from app.schemas.bgm import BgmListResponse

router = APIRouter()


@router.get("/", response_model=BgmListResponse)
def get_bgm(db: Session = Depends(get_db)):
    """Return all available BGM tracks."""
    bgm_list = db.query(Bgm).order_by(Bgm.sort_order).all()
    return {
        "bgm": bgm_list,
        "total": len(bgm_list),
    }