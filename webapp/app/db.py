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
from datetime import datetime, timedelta
from collections.abc import Generator
from pathlib import Path

from sqlalchemy import event, inspect, text as sa_text
from sqlmodel import Session, SQLModel, create_engine, select

from .config import settings
from .models import Recording as _Recording  # noqa: F401 — ensures table is registered
from .models import User as _User  # noqa: F401

log = logging.getLogger(__name__)

engine = create_engine(
    f"sqlite:///{settings.DB_PATH}",
    connect_args={"check_same_thread": False},
)


def _sqlite_pragmas(dbapi_conn, _record):
    """WAL-Modus + busy_timeout für jede neue Verbindung (2026-08-14).

    WAL (Write-Ahead-Logging) entkoppelt Leser und Schreiber: parallele
    Streaming-Transkriptionen (Progress-/Text-Updates pro Chunk), Uploads
    und Peaks-Schedules blockieren sich nicht mehr gegenseitig — der
    billigste Schritt vor einem eventuellen Postgres-Wechsel.
    journal_mode=WAL ist DB-persistent; das PRAGMA ist idempotent.
    """
    cur = dbapi_conn.cursor()
    try:
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA busy_timeout=30000")
    finally:
        cur.close()


event.listen(engine, "connect", _sqlite_pragmas)


def _purge_expired() -> None:
    """Delete public (user_id=NULL) recordings older than retention period."""
    ret = settings.PUBLIC_RETENTION_MINUTES
    if ret <= 0:
        return
    with Session(engine) as session:
        expired = session.exec(
            select(_Recording).where(
                _Recording.user_id.is_(None),
                _Recording.created_at < datetime.utcnow() - timedelta(minutes=ret),
            )
        ).all()
        for rec in expired:
            path = Path(rec.stored_path)
            if path.exists():
                path.unlink()
            # Change 014: Sidecar-Metadaten mitlöschen (Titel/Dateiname)
            try:
                from .audio_utils import sidecar_path

                sidecar_path(rec.stored_path).unlink(missing_ok=True)
            except Exception:
                pass
            session.delete(rec)
        if expired:
            log.info("Purged %d expired public recording(s) (>%d min)", len(expired), ret)
        session.commit()


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
                if default is not None and not default.is_scalar:
                    # Column uses default_factory (Python-side lambda) — SQLite can't
                    # use it as DEFAULT in ALTER TABLE. Force NULL to allow addition.
                    nullable = "NULL"
                    dfl = ""
                else:
                    arg = default.arg if default is not None else None
                    if isinstance(arg, str):
                        # String-Defaults MÜSSEN quotiert werden, sonst crasht SQLite
                        # bei Sonderzeichen ("pk-python", "application/octet-stream").
                        dfl = f"DEFAULT '{arg.replace(chr(39), chr(39)*2)}'"
                    elif arg is None:
                        dfl = "DEFAULT NULL"
                    elif isinstance(arg, bool):
                        dfl = f"DEFAULT {1 if arg else 0}"
                    else:
                        dfl = f"DEFAULT {arg}"
                sql = f"ALTER TABLE {table} ADD COLUMN {col} {col_type} {nullable} {dfl}"
                log.info("Auto-migrate: %s", sql.strip())
                session.exec(sa_text(sql))  # type: ignore[arg-type]

    # Fix old recordings stuck in "processing" — reset to "uploaded" (no text = never transcribed)
    fix = sa_text("UPDATE recording SET status='uploaded' WHERE status='processing' AND text IS NULL")
    session.exec(fix)  # type: ignore[arg-type]
    log.info("Auto-migrate: reset stale 'processing' → 'uploaded'")

    # Stale-Processing-Watchdog lebt in stale_jobs.sweep_stale_processing
    # (Heartbeat-basiert via updated_at, POLYSCHNACK_STALE_PROCESSING_MINUTES,
    # laeuft periodisch im Retention-Loop in main.py). Kein created_at-Sweep
    # hier: ein fixes 29-min-Limit wuerde lange Laeufe (Chunking, Alignment,
    # 82-min-Dateien) faelschlich als "out of memory" killen.

    # Backend-ID-Umbau (2026-08): alte Adapter-IDs → neue Container-Schema-IDs.
    # Alte Namen: pk-python, pk-cpp, qwen3-asr, ark-asr, moonshine-de, canary-asr.
    backend_rename = {
        "pk-python": "ps-pk-onnx",
        "pk-cpp": "crispr-pk-cpp",
        "qwen3-asr": "crispr-qwen3",
        "ark-asr": "crispr-ark",
        "moonshine-de": "crispr-moonshine-de",
        "canary-asr": "crispr-canary",
        "voxtral": "ps-voxtral",
    }
    for old, new in backend_rename.items():
        session.exec(
            sa_text("UPDATE recording SET backend=:new WHERE backend=:old").bindparams(
                new=new, old=old
            )
        )  # type: ignore[arg-type]
    log.info("Auto-migrate: Backend-IDs auf Container-Schema umbenannt")

    session.commit()


def init_db() -> None:
    """Create tables, run auto-migrations, ensure audio dir, purge expired public recordings."""
    settings.AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    # Change 008: Standard-Export-Templates nach DATA_DIR/export_templates/
    # schreiben (falls fehlend) — eigene Templates bleiben unberührt.
    from .export import ensure_standard_templates

    ensure_standard_templates(settings.DATA_DIR / "export_templates")
    SQLModel.metadata.create_all(engine)
    _auto_migrate()
    _purge_expired()


def get_session() -> Generator[Session, None, None]:
    """Yield a SQLModel session; commit/rollback is the caller's responsibility."""
    with Session(engine) as session:
        yield session
