"""Zentrale Zugriffskontrolle für Recordings (Sharing, Task A1/A4).

Rechte-Hierarchie: read < write < full.
- Owner (rec.user_id == uid) → "full"
- Legacy-public (rec.user_id is None) → "read" für alle
- Shares (RecordingShare) → Level aus der Share-Tabelle (Task A4)
"""
from __future__ import annotations

from typing import Optional

from fastapi import HTTPException

LEVELS = {"read": 1, "write": 2, "full": 3}


def get_access_level(session, rec, uid: Optional[int], cap: Optional[str] = None) -> Optional[str]:
    """Effektiver Zugriffslevel für *uid* auf *rec*; None = kein Zugriff.

    ``cap`` (Task C3): Rechte-Deckel eines API-Keys — der Level wird nie
    höher als ``cap``, selbst wenn Owner/Share mehr erlauben würden.
    """
    if rec.user_id is None:
        level = "read"  # Legacy-public: für alle lesbar
    elif uid is not None and rec.user_id == uid:
        level = "full"
    else:
        share = _find_share(session, rec.id, uid) if uid is not None else None
        level = share.level if share else None
    if level is not None and cap is not None and LEVELS.get(level, 0) > LEVELS.get(cap, 0):
        return cap
    return level


def _find_share(session, rec_id: int, uid: Optional[int]):
    """Share-Zeile für (rec, uid); Task A4 füllt die Tabelle."""
    if session is None:
        return None
    from sqlmodel import select

    from .models import RecordingShare

    return session.exec(
        select(RecordingShare).where(
            RecordingShare.rec_id == rec_id, RecordingShare.user_id == uid
        )
    ).first()


def require_level(need: str, have: Optional[str]) -> bool:
    return have is not None and LEVELS.get(have, 0) >= LEVELS[need]


def ensure(need: str, have: Optional[str]) -> None:
    if not require_level(need, have):
        raise HTTPException(status_code=403, detail=f"requires at least '{need}' access")


def ensure_access(session, rec, uid: Optional[int], need: str, cap: Optional[str] = None) -> None:
    ensure(need, get_access_level(session, rec, uid, cap=cap))
