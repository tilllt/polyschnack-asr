"""Harte Limits für anonyme User (Task B5) — Dauer, Upload-Größe, Disk-Quota."""
from __future__ import annotations

from typing import Optional

from fastapi import HTTPException
from sqlmodel import Session, func, select

from .config import settings
from .models import Recording


def enforce_anon_limits(session: Session, user, size_bytes: int,
                        duration_s: Optional[float] = None) -> None:
    """Wirft 409/413, wenn ein anonymer User seine Limits überschreitet.

    Registrierte User (kind=oidc) und None (kein User) sind unbegrenzt.
    """
    if user is None or getattr(user, "kind", "oidc") != "anonymous":
        return
    if duration_s is not None and duration_s > settings.POLYSCHNACK_ANON_MAX_DURATION_S:
        raise HTTPException(
            status_code=409,
            detail=f"maximale Transkriptionsdauer für anonyme Nutzung: "
                   f"{settings.POLYSCHNACK_ANON_MAX_DURATION_S}s",
        )
    if size_bytes > settings.POLYSCHNACK_ANON_MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(
            status_code=413,
            detail=f"Datei zu groß für anonyme Nutzung "
                   f"(max {settings.POLYSCHNACK_ANON_MAX_UPLOAD_MB} MB)",
        )
    used = session.exec(
        select(func.sum(Recording.size_bytes)).where(Recording.user_id == user.id)
    ).first() or 0
    if (used or 0) + size_bytes > settings.POLYSCHNACK_ANON_MAX_DISK_MB * 1024 * 1024:
        raise HTTPException(
            status_code=413,
            detail=f"Speicherlimit für anonyme Nutzung erreicht "
                   f"(max {settings.POLYSCHNACK_ANON_MAX_DISK_MB} MB)",
        )
