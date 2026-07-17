"""Path resolution that works both in dev and in a PyInstaller build.

Frozen layout (onedir):
    highlight-ai/
      highlight-ai.exe        <- writable data lives in data/ next to it
      data/                      (clips, frames, uploads, thumbnails, DB)
      _internal/              <- read-only bundled resources (sys._MEIPASS)
        static/  assets/  ml/

Dev layout: everything resolves into the repo exactly as before.
"""
import sys
from pathlib import Path

FROZEN = getattr(sys, "frozen", False)

if FROZEN:
    _RES = Path(getattr(sys, "_MEIPASS", str(Path(sys.executable).parent / "_internal")))
    DATA_DIR = Path(sys.executable).parent / "data"
    STATIC_DIR = _RES / "static"
    ASSETS_DIR = _RES / "assets"
    MODELS_DIR = _RES / "ml" / "models"
else:
    _BACKEND = Path(__file__).resolve().parent.parent      # backend/
    _ROOT = _BACKEND.parent                                # project root
    DATA_DIR = _BACKEND
    STATIC_DIR = _BACKEND / "static"
    ASSETS_DIR = _ROOT / "assets"
    MODELS_DIR = _ROOT / "ml" / "models"

CLIPS_DIR = DATA_DIR / "clips"
FRAMES_DIR = DATA_DIR / "frames"
THUMBNAILS_DIR = DATA_DIR / "thumbnails"
UPLOADS_DIR = DATA_DIR / "uploads"

# Runtime dirs must exist before any mount or worker touches them.
for _d in (CLIPS_DIR, FRAMES_DIR, THUMBNAILS_DIR, UPLOADS_DIR):
    _d.mkdir(parents=True, exist_ok=True)