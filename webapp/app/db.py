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
import re
from datetime import datetime, timedelta
from collections.abc import Generator
from pathlib import Path

from sqlalchemy import event, inspect, text as sa_text
from sqlalchemy.pool import NullPool
from sqlmodel import Session, SQLModel, create_engine, select

from .config import settings
from .models import Recording as _Recording  # noqa: F401 — ensures table is registered
from .models import User as _User  # noqa: F401

log = logging.getLogger(__name__)

# Change 066: NullPool statt QueuePool-Default (5 + 10 Overflow). SQLite ist
# datei-basiert — Connections sind billig (Datei-Handle), eine künstliche
# Pool-Obergrenze führt unter Last zu TimeoutError ("QueuePool limit of size
# 5 overflow 10 reached") für normale Requests. NullPool: jede Session
# bekommt eine frische Connection und gibt sie beim Schließen sofort frei.
# Parallele Leser erlaubt WAL; busy_timeout=30000 schützt Schreib-Kollisionen.
engine = create_engine(
    f"sqlite:///{settings.DB_PATH}",
    connect_args={"check_same_thread": False},
    poolclass=NullPool,
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

    # Change 099 (Etappe 2): Settings-Spalten aus `recording` entfernen —
    # die versionierte Wahrheit liegt im TranscriptionRun. Inkl. Backfill
    # (Recordings ohne Run → Baseline-Run aus den Alt-Spalten).
    _drop_legacy_settings_columns(session)

    session.commit()


_LEGACY_SETTINGS_COLUMNS = {
    "enable_vad", "enable_diarize", "diarize_num_speakers",
    "diarize_min_duration_off", "diarize_method", "enable_streaming",
    "enable_noise_reduce", "enable_enhance", "separate_backend", "enable_punctuation",
    "enable_llm_enhance", "prompt_template_id", "delivery_target_id",
    "llm_endpoint_id",
}


def _backfill_baseline_runs(session: Session) -> None:
    """Change 099: Recordings ohne Run bekommen einen Baseline-Run aus den
    Alt-Spalten (Settings) — status 'done' bei vorhandenem Text (das Ergebnis
    des Laufs wird als Result archiviert), sonst 'queued' (Upload-Plan).

    Change 103 (defensiv): Der INSERT wird dynamisch aus der Schnittmenge der
    tatsächlich existierenden Spalten von transcriptionrun ∩ recording gebaut.
    Produktions-Befund 2026-08-23: 'no such column: enable_vad' beim App-Start
    trotz _ensure_run_settings_columns — die DB kann Migrations-Zwischenzustände
    haben, die ein statischer Spaltenkatalog nicht überlebt. Mit der
    Schnittmenge kann dieser Backfill in JEDEM Zustand laufen (und ein
    Zwischenzustand wird beim nächsten Lauf automatisch nachgeholt).
    """
    _ensure_run_settings_columns(session)  # Change 103: Modell-Spalten sicherstellen
    run_cols = [r[1] for r in session.exec(
        sa_text("PRAGMA table_info(transcriptionrun)")).all()]
    rec_cols = [r[1] for r in session.exec(
        sa_text("PRAGMA table_info(recording)")).all()]
    want = ["backend", "language", "enable_vad", "vad_mode", "enable_diarize",
            "diarize_num_speakers", "diarize_min_duration_off", "diarize_method",
            "enable_streaming", "enable_noise_reduce", "enable_enhance",
            "separate_backend", "enable_punctuation", "enable_llm_enhance", "prompt_template_id",
            "delivery_target_id", "llm_endpoint_id"]
    # Modell-Defaults (SQL-Literale) für Spalten, die recording (noch) nicht hat
    defaults = {
        "backend": "'ps-pk-onnx'",
        "language": "NULL",
        "enable_vad": "0",
        "vad_mode": "'off'",  # Change 114: Legacy-Recordings ohne VAD
        "enable_diarize": "0",
        "diarize_num_speakers": "NULL",
        "diarize_min_duration_off": "NULL",
        "diarize_method": "NULL",
        "enable_streaming": "0",
        "enable_noise_reduce": "1",
        "enable_enhance": "'off'",
        "separate_backend": "'none'",
        "enable_punctuation": "0",
        "enable_llm_enhance": "0",
        "llm_endpoint_id": "NULL",
        "prompt_template_id": "NULL",
        "delivery_target_id": "NULL",
    }
    cols = [c for c in want if c in run_cols]
    if not cols:
        log.info("Change 099: Backfill übersprungen (transcriptionrun ohne "
                 "Settings-Spalten)")
        return
    col_sql = ", ".join(cols)
    sel_sql = ", ".join(
        f"COALESCE(\"{c}\", {defaults[c]})" if c in rec_cols else defaults[c]
        for c in cols)
    session.exec(sa_text(
        f"""
        INSERT INTO transcriptionrun
          (rec_id, {col_sql}, status, created_by_user_id, created_at)
        SELECT id, {sel_sql},
           CASE WHEN text IS NOT NULL THEN 'done' ELSE 'queued' END,
           user_id, created_at
        FROM recording WHERE current_run_id IS NULL
        """
    ))  # type: ignore[arg-type]
    session.exec(sa_text(
        """
        UPDATE recording SET current_run_id = (
          SELECT id FROM transcriptionrun r WHERE r.rec_id = recording.id
          ORDER BY r.id DESC LIMIT 1)
        WHERE current_run_id IS NULL
        """
    ))  # type: ignore[arg-type]
    session.exec(sa_text(
        """
        INSERT INTO transcriptionresult
          (run_id, text, segments, created_by_user_id, created_at)
        SELECT r.id, rec.text, rec.segments, rec.user_id, rec.created_at
        FROM recording rec JOIN transcriptionrun r ON r.rec_id = rec.id
        WHERE rec.current_result_id IS NULL AND rec.text IS NOT NULL
          AND r.status = 'done'
        """
    ))  # type: ignore[arg-type]
    session.exec(sa_text(
        """
        UPDATE recording SET current_result_id = (
          SELECT res.id FROM transcriptionresult res
          JOIN transcriptionrun r ON res.run_id = r.id
          WHERE r.rec_id = recording.id ORDER BY res.id DESC LIMIT 1)
        WHERE current_result_id IS NULL AND text IS NOT NULL
        """
    ))  # type: ignore[arg-type]
    session.commit()


def _ensure_run_settings_columns(session: Session) -> None:
    """Change 103: transcriptionrun aus einem 094-Stand (ohne Settings-
    Spalten) auf den 099-Modell-Stand heben.

    create_all fügt existierenden Tabellen KEINE Spalten hinzu — eine
    Produktions-DB, die mit Change 094 erstellt wurde, hat die Runs-
    Tabelle ohne enable_*/diarize_*/…-Spalten. Der 099-Backfill-INSERT
    referenziert diese Spalten → „no such column: enable_vad“ beim
    App-Start (Produktions-Befund 2026-08-23, Startup-Fail). Idempotent:
    prüft PRAGMA table_info und ergänzt nur fehlende Spalten.
    """
    cols = [r[1] for r in session.exec(
        sa_text("PRAGMA table_info(transcriptionrun)")).all()]
    add = {
        "enable_vad": "BOOLEAN NOT NULL DEFAULT 0",
        "enable_diarize": "BOOLEAN NOT NULL DEFAULT 0",
        "diarize_num_speakers": "INTEGER",
        "diarize_min_duration_off": "FLOAT",
        "diarize_method": "VARCHAR",
        "enable_streaming": "BOOLEAN NOT NULL DEFAULT 0",
        "enable_noise_reduce": "BOOLEAN NOT NULL DEFAULT 1",
        "enable_enhance": "VARCHAR NOT NULL DEFAULT 'off'",
        "separate_backend": "VARCHAR NOT NULL DEFAULT 'none'",
        "enable_punctuation": "BOOLEAN NOT NULL DEFAULT 0",
        "enable_llm_enhance": "BOOLEAN NOT NULL DEFAULT 0",
        "llm_endpoint_id": "INTEGER",
        "prompt_template_id": "INTEGER",
        "delivery_target_id": "INTEGER",
    }
    missing = [n for n in add if n not in cols]
    for name in missing:
        session.exec(sa_text(
            f"ALTER TABLE transcriptionrun ADD COLUMN {name} {add[name]}"))
    if missing:
        session.commit()
        log.info("Change 103: transcriptionrun um Settings-Spalten ergänzt (%s)",
                 ", ".join(missing))


def _drop_legacy_settings_columns(session: Session) -> None:
    """Change 099: Settings-Spalten aus `recording` entfernen.

    SQLite verweigert DROP COLUMN bei FK-beteiligten Spalten
    (prompt_template_id/delivery_target_id/llm_endpoint_id) → Table-Rebuild
    aus der sqlite_master-DDL (bereinigt), Daten-Kopie, RENAME. Indizes
    werden gesichert und neu angelegt. Idempotent: läuft nur, wenn noch
    Alt-Spalten existieren.
    """
    cols = [r[1] for r in session.exec(
        sa_text("PRAGMA table_info(recording)")).all()]
    drop = [c for c in cols if c in _LEGACY_SETTINGS_COLUMNS]
    if not drop:
        return
    drop_set = set(drop)
    log.info("Change 099: Backfill + Entfernung der Settings-Spalten %s",
             ", ".join(sorted(drop)))
    # Change 103: 094-DBs haben transcriptionrun ohne Settings-Spalten —
    # der Backfill-INSERT würde sonst beim App-Start crashen.
    _ensure_run_settings_columns(session)
    _backfill_baseline_runs(session)

    session.exec(sa_text("PRAGMA foreign_keys=OFF"))  # type: ignore[arg-type]
    idx_sql = [r[0] for r in session.exec(sa_text(
        "SELECT sql FROM sqlite_master WHERE type='index' "
        "AND tbl_name='recording' AND sql IS NOT NULL")).all()]
    ddl = session.exec(sa_text(
        "SELECT sql FROM sqlite_master WHERE type='table' "
        "AND name='recording'")).first()
    inner = ddl[0][ddl[0].index("(") + 1: ddl[0].rindex(")")]
    lines = inner.splitlines()
    out = []
    for ln in lines:
        s = ln.strip()
        if not s:
            continue
        # FK-/CONSTRAINT-Zeilen: entfernen, wenn eine referenzierte Spalte
        # in drop_set liegt (sonst komplett behalten — nie aufteilen).
        if re.match(r"^(CONSTRAINT .*)?FOREIGN KEY", s, re.IGNORECASE):
            fks = re.findall(r"FOREIGN KEY\(([^)]+)\)", s, re.IGNORECASE)
            if any(
                any(x.strip().strip('"') in drop_set for x in fk.split(","))
                for fk in fks
            ):
                continue
            out.append(ln)
            continue
        # Spaltenzeilen: in Definitionen zerlegen und nur die drop-Spalten
        # entfernen. Change 103: SQLite hängt per ALTER hinzugefügte Spalten
        # in EINER Zeile an die letzte Modell-Spaltenzeile („…current_result_id
        # INTEGER, enable_vad BOOLEAN NOT NULL DEFAULT 0, …“) — die Zeile
        # komplett zu verwerfen würde die Nicht-drop-Spalten (z. B.
        # current_result_id) mit entfernen und der CREATE schlägt fehl
        # („unknown column in foreign key definition“).
        parts = s.split(",")
        kept = []
        for part in parts:
            m = re.match(r'^\s*"?([^"\s,]+)"?', part)
            if m and m.group(1) in drop_set:
                continue
            kept.append(part)
        if kept:
            out.append(",".join(kept))
    body = "\n".join(out).rstrip()
    if body.endswith(","):
        body = body[:-1]
    session.exec(sa_text(
        "CREATE TABLE recording_099 (\n" + body + "\n)"))  # type: ignore[arg-type]
    keep = [c for c in cols if c not in drop_set]
    collist = ", ".join(f'"{c}"' for c in keep)
    session.exec(sa_text(
        f"INSERT INTO recording_099 ({collist}) SELECT {collist} FROM recording"))
    session.exec(sa_text("DROP TABLE recording"))
    session.exec(sa_text("ALTER TABLE recording_099 RENAME TO recording"))
    for s_ in idx_sql:
        session.exec(sa_text(s_))
    session.commit()
    log.info("Change 099: recording-Tabelle neu aufgebaut ohne Settings-Spalten")


def _repair_missing_uids(session: Session) -> None:
    """Change 123: Alt-Zeilen ohne uid (Migrations-Altlast, Crash-Waise)
    bekommen eine eindeutige hex-uid — sonst sind sie über die API nicht
    adressierbar (Liste zeigt uid:null → Retranscribe/Delete → 404)."""
    from sqlalchemy import text as _text

    for tbl in ("recording", "annotation"):
        try:
            session.exec(_text(
                f"UPDATE {tbl} SET uid = lower(hex(randomblob(16))) "
                f"WHERE uid IS NULL OR uid = ''"
            ))
        except Exception:  # Tabelle/Spalte fehlt in Alt-Zwischenständen
            session.rollback()
            continue
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
    with Session(engine) as session:
        _repair_missing_uids(session)  # Change 123: uid-Altlasten reparieren
    _purge_expired()


def get_session() -> Generator[Session, None, None]:
    """Yield a SQLModel session; commit/rollback is the caller's responsibility."""
    with Session(engine) as session:
        yield session


def db_health() -> tuple[bool, str]:
    """DB-Erreichbarkeit (Change 067): SELECT 1 mit kurzem Timeout.

    Returns (ok, error_msg). Wird von /health genutzt — die Webapp muss
    DB-Probleme sichtbar melden statt still leerer Ergebnisse zu liefern
    (Vorfall 2026-08-21: QueuePool-Timeout → /api/stats lieferte total 0).
    """
    from sqlalchemy import text as _text

    try:
        with Session(engine) as session:
            session.exec(_text("SELECT 1")).first()
        return True, ""
    except Exception as exc:  # noqa: BLE001 — Health muss immer antworten
        return False, str(exc)[:160]
