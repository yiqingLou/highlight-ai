"""
BGM routes - /api/bgm
"""

import time

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Bgm
from app.schemas.bgm import BgmListResponse
from app.paths import ASSETS_DIR

router = APIRouter()


@router.get("/", response_model=BgmListResponse)
def get_bgm(db: Session = Depends(get_db)):
    """Return all available BGM tracks."""
    bgm_list = db.query(Bgm).order_by(Bgm.sort_order).all()
    return {
        "bgm": bgm_list,
        "total": len(bgm_list),
    }


@router.get("/list")
def list_bgm_files():
    """List available BGM tracks under assets/bgm (name + resolved path)."""
    bgm_dir = ASSETS_DIR / "bgm"
    tracks = []
    if bgm_dir.is_dir():
        for f in sorted(bgm_dir.glob("*.mp3")):
            tracks.append({"name": f.stem, "path": str(f).replace("\\", "/")})
    return {"tracks": tracks}


@router.post("/upload", status_code=201)
async def upload_bgm(file: UploadFile):
    """Accept an .mp3 upload and store it under assets/bgm."""
    if not file.filename or not file.filename.lower().endswith(".mp3"):
        raise HTTPException(status_code=400, detail="Only .mp3 files are supported")

    bgm_dir = ASSETS_DIR / "bgm"
    bgm_dir.mkdir(parents=True, exist_ok=True)

    dest = bgm_dir / file.filename
    if dest.exists():
        dest = bgm_dir / f"{dest.stem}_{int(time.time())}{dest.suffix}"

    CHUNK = 4 * 1024 * 1024
    try:
        with open(dest, "wb") as out:
            while True:
                chunk = await file.read(CHUNK)
                if not chunk:
                    break
                out.write(chunk)
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"Failed to store BGM: {e}")

    return {"name": dest.stem, "path": str(dest).replace("\\", "/")}