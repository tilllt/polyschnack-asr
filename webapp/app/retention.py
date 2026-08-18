"""Retention-Sweep (Task B4) — anon-User nach Inaktivität komplett löschen."""
from __future__ import annotations

import datetime as dt

from sqlalchemy import or_
from sqlmodel import Session, select

from .config import settings
from .crud import delete_recording
from .models import Recording, RecordingShare, User


def sweep(session: Session) -> int:
    """Lösche anonyme User, deren letzte Aktivität älter als die Retention ist.

    Entfernt komplett: User-Zeile, Recordings (inkl. Audiodateien + Sidecar),
    Shares, Versionen und (falls vorhanden, Teil C) API-Keys. Rückgabe:
    Anzahl gelöschter User.

    Change 014 (2026-08-18): Der Owner-Fallback ``owner_user_id`` wird
    mitberücksichtigt — Recordings, die per Recovery-Restore einem anon-
    User zugeordnet wurden (user_id=None, owner_user_id=uid), müssen
    ebenfalls mit der Retention verschwinden. Sonst blieben sie ewig
    liegen (Datenschutz).
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
        recs = session.exec(
            select(Recording).where(
                or_(Recording.user_id == u.id, Recording.owner_user_id == u.id)
            )
        ).all()
        for r in recs:
            try:
                from pathlib import Path

                Path(r.stored_path).unlink(missing_ok=True)
                # Change 014: Sidecar-Metadaten mitlöschen (Titel/Dateiname)
                try:
                    from .audio_utils import sidecar_path

                    sidecar_path(r.stored_path).unlink(missing_ok=True)
                except Exception:
                    pass
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
