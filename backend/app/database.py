"""
SQLAlchemy database setup.

This module defines:
- The SQLite engine (where the .db file lives)
- The session factory (used by routes to query)
- The Base class (all ORM models inherit from this)
"""

from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker


# Database file location
# Stored in backend/highlight_ai.db (gitignored)
BACKEND_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BACKEND_DIR / "highlight_ai.db"
DATABASE_URL = f"sqlite:///{DB_PATH}"


# Create SQLAlchemy engine
# check_same_thread=False is required for SQLite + FastAPI
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
)


# Session factory
# Each request will create its own Session
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# Base class for all ORM models
# Every model in app/models/ will inherit from this
Base = declarative_base()


def get_db():
    """
    FastAPI dependency: provide a database session per request.
    Automatically closes the session after the request finishes.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()