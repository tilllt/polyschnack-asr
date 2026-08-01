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


def _current_user(request: Request) -> Optional[int]:
    if not settings.OIDC_ENABLED:
        return None
    return request.session.get("user_id")


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
    ensure_access(session, rec, _current_user(request), "read")
    return [
        {
            "version_no": v.version_no,
            "kind": v.kind,
            "backend": v.backend,
            "language": v.language,
            "created_at": v.created_at.isoformat(),
            "created_by_user_id": v.created_by_user_id,
        }
        for v in list_versions(session, rec.id)
    ]


@router.get("/recordings/{rid}/versions/{v_no}/diff")
def diff_endpoint(rid: str, v_no: int, request: Request,
                  session: Session = Depends(get_session),
                  frm: Optional[int] = None) -> dict:
    """Diff zwischen zwei Versionen (Standard: *v_no* gegen ihre Vorgängerin)."""
    rec = get_recording_by_uid(session, rid)
    if rec is None:
        raise HTTPException(status_code=404, detail="not found")
    ensure_access(session, rec, _current_user(request), "read")
    versions = list_versions(session, rec.id)
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
    uid = _current_user(request)
    ensure_access(session, rec, uid, "write")
    v = _get_version(session, rec.id, v_no)
    rec.text = v.text
    rec.segments = list(v.segments) if v.segments else None
    session.add(rec)
    session.commit()
    session.refresh(rec)
    snapshot(session, rec, "restore", user_id=uid)
    return {"restored": v_no, "version_no": rec.id}
