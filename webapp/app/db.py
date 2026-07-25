"""Database engine, session factory, and schema initialisation.

Importing this module creates the SQLAlchemy engine.  Call ``init_db()``
once at application startup (inside the FastAPI lifespan) to ensure all
tables exist, missing columns are added, and the audio directory is present.

Auto-migration (SQLite only)
----------------------------
``_auto_migrate()`` runs ``ALTER TABLE ADD COLUMN`` for any column that
exists in the SQLModel definition but is missing from the live schema.
This handles the common case of adding nullable or default-valued columns.
For destructive changes (renames, type changes) the database must be re-created.
"""
from __future__ import annotations

import logging
from collections.abc import Generator

from sqlalchemy import inspect
from sqlmodel import Session, SQLModel, create_engine

from .config import settings
from .models import Recording as _Recording  # noqa: F401 — ensures table is registered
from .models import User as _User  # noqa: F401

log = logging.getLogger(__name__)

engine = create_engine(
    f"sqlite:///{settings.DB_PATH}",
    connect_args={"check_same_thread": False},
)


def _missing_columns(table: str) -> list[str]:
    """Return column names that exist in the SQLModel but not the live table."""
    inspector = inspect(engine)
    existing = {c["name"] for c in inspector.get_columns(table)}
    model_table = SQLModel.metadata.tables.get(table)
    if model_table is None:
        return []
    model_cols = {c.name for c in model_table.columns}
    return [c for c in model_cols if c not in existing]


def _auto_migrate() -> None:
    """Idempotently add missing columns to existing tables."""
    with Session(engine) as session:
        inspector = inspect(engine)
        for table in inspector.get_table_names():
            missing = _missing_columns(table)
            if not missing:
                continue
            for col in missing:
                model_col = SQLModel.metadata.tables[table].columns[col]
                col_type = model_col.type
                nullable = "NULL" if model_col.nullable else "NOT NULL"
                default = model_col.default
                dfl = f"DEFAULT {default.arg}" if default is not None else ""
                sql = f"ALTER TABLE {table} ADD COLUMN {col} {col_type} {nullable} {dfl}"
                log.info("Auto-migrate: %s", sql.strip())
                session.exec(sql)  # type: ignore[arg-type]

                # Fix old recordings stuck in "processing" — reset to "uploaded" (no text = never transcribed)
                fix = "UPDATE recording SET status='uploaded' WHERE status='processing' AND text IS NULL"
                session.exec(fix)  # type: ignore[arg-type]
                log.info("Auto-migrate: reset stale 'processing' → 'uploaded'")
        session.commit()


def init_db() -> None:
    """Create tables, run auto-migrations, and ensure the audio directory exists."""
    settings.AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    SQLModel.metadata.create_all(engine)
    _auto_migrate()


def get_session() -> Generator[Session, None, None]:
    """Yield a SQLModel session; commit/rollback is the caller's responsibility."""
    with Session(engine) as session:
        yield session
