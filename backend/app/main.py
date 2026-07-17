"""
highlight-ai backend - clean modular structure.

Run with: uvicorn app.main:app --reload --port 8000

All endpoints organized into routers under app/routes/:
  /api/highlights/*  (routes/highlights.py)
  /api/tasks/*       (routes/tasks.py)
  /api/bgm           (routes/bgm.py)
  /api/settings      (routes/settings.py)
  /api/stats         (routes/stats.py)
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.paths import CLIPS_DIR, STATIC_DIR
from app.database import Base, engine
from app import models  # noqa: F401 - import so every model registers on Base

# All endpoint routers
from app.routes import highlights as highlights_routes
from app.routes import tasks as tasks_routes
from app.routes import bgm as bgm_routes
from app.routes import settings as settings_routes
from app.routes import stats as stats_routes

app = FastAPI(
    title="highlight-ai API",
    description="AI-powered game highlight clipping tool",
    version="0.4.0",
)

# Allow frontend (localhost:3000) to call this backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================
# Create tables if they don't exist yet
# ============================================
# A packaged build starts with an empty data/ dir next to the exe, so its DB
# file has no tables at all. create_all is a no-op once they exist, so this is
# safe to run on every startup.
Base.metadata.create_all(bind=engine)

# ============================================
# Include all routers
# ============================================
app.include_router(highlights_routes.router, prefix="/api/highlights", tags=["highlights"])
app.include_router(tasks_routes.router, prefix="/api/tasks", tags=["tasks"])
app.include_router(bgm_routes.router, prefix="/api/bgm", tags=["bgm"])
app.include_router(settings_routes.router, prefix="/api/settings", tags=["settings"])
app.include_router(stats_routes.router, prefix="/api/stats", tags=["stats"])

# ============================================
# Frontend (static single-page app)
# ============================================
app.mount("/clips", StaticFiles(directory=str(CLIPS_DIR)), name="clips")
app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")