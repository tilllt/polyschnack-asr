"""CRUD helpers — all database operations as pure functions.

Every function receives an open ``Session`` and operates within it.
No HTTP calls, no business logic, no side effects beyond the DB.
"""
from __future__ import annotations

import datetime as dt
from typing import Any, Dict, List, Optional

from sqlmodel import Session, select

from .models import Recording, User


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
    enable_streaming: bool = False,
    enable_noise_reduce: bool = True,
    content_hash: Optional[str] = None,
    duration_s: Optional[float] = None,
    user_id: Optional[int] = None,
) -> Recording:
    """Insert a new Recording row with status='processing' and return it."""
    rec = Recording(
        original_name=original_name,
        stored_path=stored_path,
        mime=mime,
        size_bytes=size_bytes,
        duration_s=duration_s,
        status="uploaded",
        batch_id=batch_id,
        recorded_at=recorded_at,
        source=source,
        enable_vad=enable_vad,
        enable_diarize=enable_diarize,
        enable_streaming=enable_streaming,
        enable_noise_reduce=enable_noise_reduce,
        content_hash=content_hash,
        user_id=user_id,
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


def get_recording_by_uid(session: Session, uid: str) -> Optional[Recording]:
    """Return the Recording with *uid*, or ``None`` if not found."""
    return session.exec(select(Recording).where(Recording.uid == uid)).first()


def list_recordings(session: Session, q: Optional[str] = None, user_id: Optional[int] = None) -> List[Recording]:
    """Return recordings ordered by newest first.

    - *user_id* = ``None`` → only recordings with no owner (public/shared space)
    - *user_id* = ``int`` → only recordings belonging to that user (private space)
    """
    stmt = select(Recording)
    if user_id is not None:
        stmt = stmt.where(Recording.user_id == user_id)
    else:
        stmt = stmt.where(Recording.user_id.is_(None))
    if q:
        term = f"%{q.lower()}%"
        stmt = stmt.where(
            Recording.original_name.ilike(term) | Recording.text.ilike(term)  # type: ignore[union-attr]
        )
    stmt = stmt.order_by(Recording.created_at.desc())  # type: ignore[arg-type]
    return list(session.exec(stmt).all())


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------


def set_processing(session: Session, rec_id: int) -> Optional[Recording]:
    """Reset a recording to processing state, clearing previous results.

    ``duration_s`` is NOT cleared here so the frontend can show a meaningful
    ETA from the upload-time estimate while the ASR worker is still starting up.
    The worker will overwrite it with the decoded duration when it finishes.
    ``progress_pct`` starts at 1 (not 0) so the frontend does not hide the ETA.
    """
    rec = session.get(Recording, rec_id)
    if rec is None:
        return None
    rec.status = "processing"
    rec.text = None
    rec.segments = None
    rec.language = None
    rec.error = None
    # keep duration_s — the upload already gave us a rough estimate for ETA
    rec.processing_ms = None
    rec.progress_pct = 1  # 1 instead of 0 so fmtETA can compute
    # Clear preview path (will be re-generated on next process_recording)
    rec.preview_path = None
    rec.preview_size_bytes = None
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
    progress_pct: int = 100,
    waveform_peaks: Optional[List[float]] = None,
    preview_path: Optional[str] = None,
    preview_size_bytes: Optional[int] = None,
) -> Optional[Recording]:
    """Persist the transcription result (success or failure) for *rec_id*."""
    rec = session.get(Recording, rec_id)
    if rec is None:
        return None
    rec.status = status
    rec.text = text
    if duration_s is not None:
        rec.duration_s = duration_s
    rec.language = language
    rec.segments = segments
    rec.processing_ms = processing_ms
    rec.error = error
    rec.progress_pct = progress_pct
    if waveform_peaks is not None:
        rec.waveform_peaks = waveform_peaks
    rec.preview_path = preview_path
    rec.preview_size_bytes = preview_size_bytes
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


def get_stats(session: Session, user_id: Optional[int] = None) -> Dict[str, Any]:
    """Return aggregate counts and totals across all recordings (or per user)."""
    stmt = select(Recording)
    if user_id is not None:
        stmt = stmt.where(Recording.user_id == user_id)
    else:
        stmt = stmt.where(Recording.user_id.is_(None))
    rows = list(session.exec(stmt).all())
    total = len(rows)
    done = sum(1 for r in rows if r.status == "done")
    processing = sum(1 for r in rows if r.status == "processing")
    uploaded = sum(1 for r in rows if r.status == "uploaded")
    failed = sum(1 for r in rows if r.status == "failed")
    total_audio_s = sum(r.duration_s or 0.0 for r in rows)
    total_processing_ms = sum(r.processing_ms or 0.0 for r in rows)
    return {
        "total": total,
        "done": done,
        "processing": processing,
        "uploaded": uploaded,
        "failed": failed,
        "total_audio_s": total_audio_s,
        "total_processing_ms": total_processing_ms,
    }


# ---------------------------------------------------------------------------
# User CRUD
# ---------------------------------------------------------------------------


def get_or_create_user(
    session: Session,
    *,
    sub: str,
    preferred_username: Optional[str] = None,
    email: Optional[str] = None,
    name: Optional[str] = None,
) -> User:
    user = session.exec(select(User).where(User.sub == sub)).first()
    if user:
        if preferred_username:
            user.preferred_username = preferred_username
        if email:
            user.email = email
        if name:
            user.name = name
        session.add(user)
        return user
    user = User(
        sub=sub,
        preferred_username=preferred_username,
        email=email,
        name=name,
    )
    session.add(user)
    session.flush()
    return user


def get_user(session: Session, user_id: int) -> Optional[User]:
    return session.get(User, user_id)


def set_progress(session: Session, rec_id: int, pct: int) -> None:
    """Update progress_pct for a recording (no refresh needed)."""
    rec = session.get(Recording, rec_id)
    if rec:
        rec.progress_pct = pct
        session.add(rec)
        session.commit()
