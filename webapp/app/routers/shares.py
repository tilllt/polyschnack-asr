"""Share-API (Task A3) — Shares verwalten: Owner oder Full-Mitglied.

Ein Share gewährt einem User Zugriff auf ein fremdes Recording mit
Level read|write|full (gleiche Ebenen wie in permissions.py).
"""
from __future__ import annotations

from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlmodel import Session, select

from ..config import settings
from ..crud import get_recording_by_uid
from ..db import get_session
from ..models import RecordingShare, User
from ..permissions import ensure_access, get_access_level

router = APIRouter(prefix="/api")


def _current_user(request: Request) -> Optional[int]:
    if not settings.OIDC_ENABLED:
        return None
    return request.session.get("user_id")


class ShareCreate(BaseModel):
    user: str  # preferred_username | email | numeric id
    level: Literal["read", "write", "full"] = "read"


class ShareUpdate(BaseModel):
    level: Literal["read", "write", "full"]


def _resolve_user(session: Session, ref: str) -> Optional[User]:
    if ref.isdigit():
        return session.get(User, int(ref))
    return session.exec(
        select(User).where((User.preferred_username == ref) | (User.email == ref))
    ).first()


def _get_share(session: Session, rec: Recording, share_id: int) -> RecordingShare:
    share = session.get(RecordingShare, share_id)
    if share is None or share.rec_id != rec.id:
        raise HTTPException(status_code=404, detail="share not found")
    return share


@router.get("/recordings/{rid}/shares")
def list_shares(rid: str, request: Request, session: Session = Depends(get_session)) -> list:
    rec = get_recording_by_uid(session, rid)
    if rec is None:
        raise HTTPException(status_code=404, detail="recording not found")
    uid = _current_user(request)
    ensure_access(session, rec, uid, "full")
    shares = session.exec(
        select(RecordingShare).where(RecordingShare.rec_id == rec.id)
    ).all()
    return [
        {
            "share_id": sh.id,
            "user": sh.user_id,
            "user_name": (u.name or u.preferred_username) if (u := session.get(User, sh.user_id)) else None,
            "level": sh.level,
            "created_at": sh.created_at.isoformat(),
        }
        for sh in shares
    ]


@router.post("/recordings/{rid}/shares")
def create_share(
    rid: str,
    body: ShareCreate,
    request: Request,
    session: Session = Depends(get_session),
) -> dict:
    rec = get_recording_by_uid(session, rid)
    if rec is None:
        raise HTTPException(status_code=404, detail="recording not found")
    uid = _current_user(request)
    ensure_access(session, rec, uid, "full")
    target = _resolve_user(session, body.user)
    if target is None:
        raise HTTPException(status_code=404, detail="user not found")
    if target.id == rec.user_id:
        raise HTTPException(status_code=409, detail="the owner cannot be shared")
    existing = session.exec(
        select(RecordingShare).where(
            RecordingShare.rec_id == rec.id, RecordingShare.user_id == target.id
        )
    ).first()
    if existing:
        existing.level = body.level
        session.add(existing)
        session.commit()
        session.refresh(existing)
        return {"share_id": existing.id, "user_id": target.id, "level": existing.level}
    share = RecordingShare(rec_id=rec.id, user_id=target.id, level=body.level)
    session.add(share)
    session.commit()
    session.refresh(share)
    return {"share_id": share.id, "user_id": target.id, "level": share.level}


@router.put("/recordings/{rid}/shares/{share_id}")
def update_share(
    rid: str, share_id: int, body: ShareUpdate, request: Request,
    session: Session = Depends(get_session),
) -> dict:
    rec = get_recording_by_uid(session, rid)
    if rec is None:
        raise HTTPException(status_code=404, detail="recording not found")
    uid = _current_user(request)
    ensure_access(session, rec, uid, "full")
    share = _get_share(session, rec, share_id)
    share.level = body.level
    session.add(share)
    session.commit()
    return {"share_id": share.id, "level": share.level}


@router.delete("/recordings/{rid}/shares/{share_id}")
def delete_share(
    rid: str, share_id: int, request: Request, session: Session = Depends(get_session),
) -> dict:
    rec = get_recording_by_uid(session, rid)
    if rec is None:
        raise HTTPException(status_code=404, detail="recording not found")
    uid = _current_user(request)
    ensure_access(session, rec, uid, "full")
    share = _get_share(session, rec, share_id)
    session.delete(share)
    session.commit()
    return {"deleted": share_id}
