"""Delivery-Target-CRUD (Task D3) — email | webdav, Passwörter verschlüsselt."""
from __future__ import annotations

import json
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlmodel import Session, select

from ..crypto import encrypt
from ..db import get_session
from ..models import DeliveryTarget

router = APIRouter(prefix="/api")


class TargetCreate(BaseModel):
    name: str
    kind: Literal["email", "webdav"]
    config: dict


class TargetUpdate(BaseModel):
    name: Optional[str] = None
    config: Optional[dict] = None


def _current_user(request, session=None) -> Optional[int]:
    from ..identity import current_identity

    return current_identity(request, session).user.id


def _mask(config: dict) -> dict:
    """Passwort nie an den Client zurückgeben."""
    if "password" in config:
        config = {**config, "password": "********"}
    return config


def _get_own(session: Session, target_id: int, user_id: int) -> DeliveryTarget:
    t = session.get(DeliveryTarget, target_id)
    if t is None or t.user_id != user_id:
        raise HTTPException(status_code=404, detail="target not found")
    return t


def _store_config(config: dict) -> str:
    cfg = dict(config)
    if cfg.get("password"):
        cfg["password"] = encrypt(cfg["password"])
    return json.dumps(cfg)


@router.post("/targets")
def create_target(body: TargetCreate, request: Request,
                  session: Session = Depends(get_session)) -> dict:
    uid = _current_user(request, session)
    t = DeliveryTarget(user_id=uid, name=body.name, kind=body.kind,
                       config=_store_config(body.config))
    session.add(t)
    session.commit()
    session.refresh(t)
    return {"target_id": t.id, "name": t.name, "kind": t.kind,
            "config": _mask(json.loads(t.config or "{}"))}


@router.get("/targets")
def list_targets(request: Request, session: Session = Depends(get_session)) -> list:
    uid = _current_user(request, session)
    ts = session.exec(select(DeliveryTarget).where(DeliveryTarget.user_id == uid)).all()
    return [{"target_id": t.id, "name": t.name, "kind": t.kind,
             "config": _mask(json.loads(t.config or "{}"))} for t in ts]


@router.put("/targets/{target_id}")
def update_target(target_id: int, body: TargetUpdate, request: Request,
                  session: Session = Depends(get_session)) -> dict:
    uid = _current_user(request, session)
    t = _get_own(session, target_id, uid)
    if body.name is not None:
        t.name = body.name
    if body.config is not None:
        t.config = _store_config(body.config)
    session.add(t)
    session.commit()
    return {"target_id": t.id, "name": t.name, "kind": t.kind,
            "config": _mask(json.loads(t.config or "{}"))}


@router.delete("/targets/{target_id}")
def delete_target(target_id: int, request: Request,
                  session: Session = Depends(get_session)) -> dict:
    uid = _current_user(request, session)
    t = _get_own(session, target_id, uid)
    session.delete(t)
    session.commit()
    return {"deleted": target_id}
