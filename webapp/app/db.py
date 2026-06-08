"""Database engine, session factory, and schema initialisation.

Importing this module creates the SQLAlchemy engine.  Call ``init_db()``
once at application startup (inside the FastAPI lifespan) to ensure all
tables exist and the audio directory is present on disk.
"""
from __future__ import annotations

from collections.abc import Generator

from sqlmodel import Session, SQLModel, create_engine

from .config import settings
from .models import Recording as _Recording  # noqa: F401 — ensures table is registered

engine = create_engine(
    f"sqlite:///{settings.DB_PATH}",
    connect_args={"check_same_thread": False},
)


def init_db() -> None:
    """Create tables and the audio directory if they do not exist yet."""
    settings.AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    SQLModel.metadata.create_all(engine)


def get_session() -> Generator[Session, None, None]:
    """Yield a SQLModel session; commit/rollback is the caller's responsibility."""
    with Session(engine) as session:
        yield session
