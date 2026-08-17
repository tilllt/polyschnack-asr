"""Versions-API (Task A7): Liste, Diff zwischen Versionen, Restore."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlmodel import Session

from ..config import settings
from ..crud import get_recording_by_uid
from ..db import get_session
from ..permissions import ensure_access
from ..versions import get_diff, list_versions, snapshot

router = APIRouter(prefix="/api")


def _current_user(request, session=None) -> Optional[int]:
    from ..identity import current_identity

    identity = current_identity(request, session)
    if identity is None or getattr(identity, "user", None) is None:
        return None
    return identity.user.id


def _key_cap(request, session=None) -> Optional[str]:
    from ..identity import current_identity

    identity = current_identity(request, session)
    if identity is None:
        return None
    return identity.key_level


def _anon_since(rec, uid: Optional[int]) -> Optional[object]:
    """Versions-Gating für Anon-Share-Link-Zugriffe.

    Nur wenn der Zugriff NICHT vom Owner kommt (uid fehlt oder != rec.user_id)
    UND die Recording einen Anon-Link hat, werden Versionen vor ``shared_at``
    ausgeblendet („discarded"). Der Owner sieht immer alle Versionen.
    """
    if not getattr(rec, "share_token", False):
        return None
    if rec.user_id is not None and uid == rec.user_id:
        return None  # Owner → alle Versionen
    return getattr(rec, "shared_at", None)


def _get_version(session: Session, rec_id: int, v_no: int):
    for v in list_versions(session, rec_id):
        if v.version_no == v_no:
            return v
    raise HTTPException(status_code=404, detail="version not found")


@router.get("/recordings/{rid}/versions")
def list_versions_endpoint(rid: str, request: Request,
                           session: Session = Depends(get_session)) -> list:
    rec = get_recording_by_uid(session, rid)
    if rec is None:
        raise HTTPException(status_code=404, detail="not found")
    uid = _current_user(request, session)
    ensure_access(session, rec, uid, "read",
                  cap=_key_cap(request, session))
    since = _anon_since(rec, uid)
    return [
        {
            "version_no": v.version_no,
            "kind": v.kind,
            "backend": v.backend,
            "language": v.language,
            "created_at": v.created_at.isoformat(),
            "created_by_user_id": v.created_by_user_id,
        }
        for v in list_versions(session, rec.id, since=since)
    ]


@router.get("/recordings/{rid}/versions/{v_no}/diff")
def diff_endpoint(rid: str, v_no: int, request: Request,
                  session: Session = Depends(get_session),
                  frm: Optional[int] = None) -> dict:
    """Diff zwischen zwei Versionen (Standard: *v_no* gegen ihre Vorgängerin)."""
    rec = get_recording_by_uid(session, rid)
    if rec is None:
        raise HTTPException(status_code=404, detail="not found")
    uid = _current_user(request, session)
    ensure_access(session, rec, uid, "read",
                  cap=_key_cap(request, session))
    versions = list_versions(session, rec.id, since=_anon_since(rec, uid))
    b = next((v for v in versions if v.version_no == v_no), None)
    if b is None:
        raise HTTPException(status_code=404, detail="version not found")
    if frm is None:
        a = next((v for v in versions if v.version_no < v_no), None)
        if a is None:
            return {"from": None, "to": v_no, "diff": []}
    else:
        a = next((v for v in versions if v.version_no == frm), None)
        if a is None:
            raise HTTPException(status_code=404, detail="from-version not found")
    return {"from": a.version_no, "to": b.version_no, "diff": get_diff(a, b)}


@router.post("/recordings/{rid}/versions/{v_no}/restore")
def restore_endpoint(rid: str, v_no: int, request: Request,
                     session: Session = Depends(get_session)) -> dict:
    """Inhalt einer alten Version wiederherstellen (neue Version kind=restore)."""
    rec = get_recording_by_uid(session, rid)
    if rec is None:
        raise HTTPException(status_code=404, detail="not found")
    uid = _current_user(request, session)
    ensure_access(session, rec, uid, "write", cap=_key_cap(request, session))
    v = _get_version(session, rec.id, v_no)
    rec.text = v.text
    rec.segments = list(v.segments) if v.segments else None
    # Change 009: Restore stellt einen alten ASR-Stand wieder her —
    # manuelle Aufteilung ist damit aufgehoben (Auto-Aufteilung gilt wieder).
    rec.segments_manual = False
    session.add(rec)
    session.commit()
    session.refresh(rec)
    snapshot(session, rec, "restore", user_id=uid)
    return {"restored": v_no, "version_no": rec.id}
