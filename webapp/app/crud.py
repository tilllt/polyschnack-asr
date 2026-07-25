"""CRUD helpers — all database operations as pure functions.

Every function receives an open ``Session`` and operates within it.
No HTTP calls, no business logic, no side effects beyond the DB.
"""
from __future__ import annotations

import datetime as dt
from typing import Any, Dict, List, Optional

from sqlmodel import Session, select

from .models import Recording


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


def create_recording(
    session: Session,
    *,
    original_name: str,
    stored_path: str,
    mime: str,
    size_bytes: int,
    batch_id: Optional[str] = None,
    recorded_at: Optional[dt.datetime] = None,
    source: Optional[str] = None,
    enable_vad: bool = False,
    enable_diarize: bool = False,
) -> Recording:
    """Insert a new Recording row with status='processing' and return it."""
    rec = Recording(
        original_name=original_name,
        stored_path=stored_path,
        mime=mime,
        size_bytes=size_bytes,
        status="processing",
        batch_id=batch_id,
        recorded_at=recorded_at,
        source=source,
        enable_vad=enable_vad,
        enable_diarize=enable_diarize,
    )
    session.add(rec)
    session.commit()
    session.refresh(rec)
    return rec


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------


def get_recording(session: Session, rec_id: int) -> Optional[Recording]:
    """Return the Recording with *rec_id*, or ``None`` if not found."""
    return session.get(Recording, rec_id)


def list_recordings(session: Session, q: Optional[str] = None) -> List[Recording]:
    """Return all recordings ordered by newest first.

    When *q* is provided, only rows whose ``original_name`` or ``text``
    contain *q* (case-insensitive) are returned.
    """
    stmt = select(Recording)
    if q:
        term = f"%{q.lower()}%"
        stmt = stmt.where(
            Recording.original_name.ilike(term) | Recording.text.ilike(term)  # type: ignore[union-attr]
        )
    stmt = stmt.order_by(Recording.id.desc())  # type: ignore[arg-type]
    return list(session.exec(stmt).all())


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------


def set_processing(session: Session, rec_id: int) -> Optional[Recording]:
    """Reset a recording to processing state, clearing previous results."""
    rec = session.get(Recording, rec_id)
    if rec is None:
        return None
    rec.status = "processing"
    rec.text = None
    rec.segments = None
    rec.language = None
    rec.error = None
    rec.duration_s = None
    rec.processing_ms = None
    session.add(rec)
    session.commit()
    session.refresh(rec)
    return rec


def update_result(
    session: Session,
    rec_id: int,
    *,
    status: str,
    text: str,
    duration_s: Optional[float],
    language: Optional[str],
    segments: Optional[List[Dict[str, Any]]],
    processing_ms: float,
    error: Optional[str],
) -> Optional[Recording]:
    """Persist the transcription result (success or failure) for *rec_id*."""
    rec = session.get(Recording, rec_id)
    if rec is None:
        return None
    rec.status = status
    rec.text = text
    rec.duration_s = duration_s
    rec.language = language
    rec.segments = segments
    rec.processing_ms = processing_ms
    rec.error = error
    session.add(rec)
    session.commit()
    session.refresh(rec)
    return rec


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------


def delete_recording(session: Session, rec_id: int) -> Optional[Recording]:
    """Delete the row for *rec_id* and return it (for file cleanup).

    Returns ``None`` if the row does not exist.
    """
    rec = session.get(Recording, rec_id)
    if rec is None:
        return None
    session.delete(rec)
    session.commit()
    return rec


# ---------------------------------------------------------------------------
# Aggregates
# ---------------------------------------------------------------------------


def get_stats(session: Session) -> Dict[str, Any]:
    """Return aggregate counts and totals across all recordings."""
    rows = session.exec(select(Recording)).all()
    total = len(rows)
    done = sum(1 for r in rows if r.status == "done")
    processing = sum(1 for r in rows if r.status == "processing")
    failed = sum(1 for r in rows if r.status == "failed")
    total_audio_s = sum(r.duration_s or 0.0 for r in rows)
    total_processing_ms = sum(r.processing_ms or 0.0 for r in rows)
    return {
        "total": total,
        "done": done,
        "processing": processing,
        "failed": failed,
        "total_audio_s": total_audio_s,
        "total_processing_ms": total_processing_ms,
    }
