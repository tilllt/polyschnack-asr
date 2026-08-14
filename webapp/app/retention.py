"""Retention-Sweep (Task B4) — anon-User nach Inaktivität komplett löschen."""
from __future__ import annotations

import datetime as dt

from sqlmodel import Session, select

from .config import settings
from .crud import delete_recording
from .models import Recording, RecordingShare, User


def sweep(session: Session) -> int:
    """Lösche anonyme User, deren letzte Aktivität älter als die Retention ist.

    Entfernt komplett: User-Zeile, Recordings (inkl. Audiodateien), Shares,
    Versionen und (falls vorhanden, Teil C) API-Keys. Rückgabe: Anzahl gelöschter User.
    """
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(
        minutes=settings.POLYSCHNACK_ANON_RETENTION_MINUTES
    )
    users = session.exec(
        select(User).where(
            User.kind == "anonymous",
            User.last_seen_at.isnot(None),
            User.last_seen_at < cutoff,
        )
    ).all()
    for u in users:
        for r in session.exec(select(Recording).where(Recording.user_id == u.id)).all():
            try:
                from pathlib import Path

                Path(r.stored_path).unlink(missing_ok=True)
            except Exception:
                pass
            # löscht Row + Transkript-Versionen + Shares (rec_id) + Datei-Cleanup
            delete_recording(session, r.id)
        # Shares, bei denen der gelöschte User Empfänger ist (nicht rec_id-basiert)
        for sh in session.exec(
            select(RecordingShare).where(RecordingShare.user_id == u.id)
        ).all():
            session.delete(sh)
        from . import models as _models

        ApiKey = getattr(_models, "ApiKey", None)
        if ApiKey is not None:
            for k in session.exec(select(ApiKey).where(ApiKey.user_id == u.id)).all():
                session.delete(k)
        session.delete(u)
    session.commit()
    return len(users)
