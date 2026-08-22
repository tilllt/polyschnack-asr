"""API-Keys (Teil C) — Erstellen/Listen/Ändern/Widerrufen, Owner-only."""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlmodel import Session, select

from ..db import get_session
from ..models import ApiKey, User, hash_token
from ..timeutil import iso_utc

router = APIRouter(prefix="/api")

DEFAULT_KEY_TTL_DAYS = 365


class KeyCreate(BaseModel):
    name: str = "default"
    description: Optional[str] = None
    level: Literal["read", "write", "full"] = "read"
    expires_at: Optional[datetime] = None  # None → Default 1 Jahr


class KeyUpdate(BaseModel):
    level: Literal["read", "write", "full"]


def _current_user(request, session=None) -> Optional[int]:
    from ..anon_session import current_uid

    return current_uid(request, session)


def _is_expired(key: ApiKey) -> bool:
    """Tz-tolerant: SQLite liefert naive datetimes — als UTC interpretieren."""
    if key.expires_at is None:
        return False
    exp = key.expires_at
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    return exp <= datetime.now(timezone.utc)


def _key_response(key: ApiKey) -> dict:
    return {
        "key_id": key.id,
        "name": key.name,
        "description": key.description,
        "level": key.level,
        "expires_at": iso_utc(key.expires_at) if key.expires_at else None,
        "expired": _is_expired(key),
        "created_at": iso_utc(key.created_at),
        "last_used_at": iso_utc(key.last_used_at) if key.last_used_at else None,
    }


def _get_own_key(session: Session, key_id: int, user_id: int) -> ApiKey:
    key = session.get(ApiKey, key_id)
    if key is None or key.user_id != user_id:
        raise HTTPException(status_code=404, detail="key not found")
    return key


@router.post("/keys")
def create_key(body: KeyCreate, request: Request,
               session: Session = Depends(get_session)) -> dict:
    uid = _current_user(request, session)
    if uid is None:
        raise HTTPException(status_code=401, detail="login required")
    token = secrets.token_urlsafe(32)
    expires_at = body.expires_at
    if expires_at is None:
        expires_at = datetime.now(timezone.utc) + timedelta(days=DEFAULT_KEY_TTL_DAYS)
    key = ApiKey(user_id=uid, name=body.name, description=body.description,
                 level=body.level, token_hash=hash_token(token),
                 expires_at=expires_at)
    session.add(key)
    session.commit()
    session.refresh(key)
    return {**_key_response(key), "token": token}  # Token nur hier, einmal


@router.get("/keys")
def list_keys(request: Request, session: Session = Depends(get_session)) -> list:
    uid = _current_user(request, session)
    if uid is None:
        raise HTTPException(status_code=401, detail="login required")
    keys = session.exec(select(ApiKey).where(ApiKey.user_id == uid)).all()
    return [_key_response(k) for k in keys]


@router.put("/keys/{key_id}")
def update_key(key_id: int, body: KeyUpdate, request: Request,
               session: Session = Depends(get_session)) -> dict:
    uid = _current_user(request, session)
    if uid is None:
        raise HTTPException(status_code=401, detail="login required")
    key = _get_own_key(session, key_id, uid)
    key.level = body.level
    session.add(key)
    session.commit()
    return _key_response(key)


@router.delete("/keys/{key_id}")
def delete_key(key_id: int, request: Request,
               session: Session = Depends(get_session)) -> dict:
    uid = _current_user(request, session)
    if uid is None:
        raise HTTPException(status_code=401, detail="login required")
    key = _get_own_key(session, key_id, uid)
    session.delete(key)
    session.commit()
    return {"deleted": key_id}