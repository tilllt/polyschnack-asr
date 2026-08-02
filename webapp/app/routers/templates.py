"""Prompt-Template-CRUD (Task D2) — per User, owner-only."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlmodel import Session, select

from ..db import get_session
from ..deps import require_authenticated
from ..models import PromptTemplate, User

router = APIRouter(prefix="/api", dependencies=[Depends(require_authenticated)])


class TemplateCreate(BaseModel):
    name: str
    prompt: str


class TemplateUpdate(BaseModel):
    name: Optional[str] = None
    prompt: Optional[str] = None


def _current_user(request, session=None) -> Optional[int]:
    from ..identity import current_identity

    return current_identity(request, session).user.id


def _require_oidc(session: Session, uid: Optional[int]) -> None:
    """Prompt-Templates sind ein LLM/paid-Pfad → nur registrierte User."""
    user = session.get(User, uid) if uid is not None else None
    if user is None or user.kind != "oidc":
        raise HTTPException(status_code=403, detail="login required (paid path)")


def _get_own(session: Session, tpl_id: int, user_id: int) -> PromptTemplate:
    tpl = session.get(PromptTemplate, tpl_id)
    if tpl is None or tpl.user_id != user_id:
        raise HTTPException(status_code=404, detail="template not found")
    return tpl


@router.post("/templates")
def create_template(body: TemplateCreate, request: Request,
                    session: Session = Depends(get_session)) -> dict:
    uid = _current_user(request, session)
    _require_oidc(session, uid)
    tpl = PromptTemplate(user_id=uid, name=body.name, prompt=body.prompt)
    session.add(tpl)
    session.commit()
    session.refresh(tpl)
    return {"template_id": tpl.id, "name": tpl.name, "prompt": tpl.prompt}


@router.get("/templates")
def list_templates(request: Request, session: Session = Depends(get_session)) -> list:
    uid = _current_user(request, session)
    tpls = session.exec(
        select(PromptTemplate).where(PromptTemplate.user_id == uid)
    ).all()
    return [{"template_id": t.id, "name": t.name, "prompt": t.prompt} for t in tpls]


@router.put("/templates/{tpl_id}")
def update_template(tpl_id: int, body: TemplateUpdate, request: Request,
                    session: Session = Depends(get_session)) -> dict:
    uid = _current_user(request, session)
    tpl = _get_own(session, tpl_id, uid)
    if body.name is not None:
        tpl.name = body.name
    if body.prompt is not None:
        tpl.prompt = body.prompt
    session.add(tpl)
    session.commit()
    return {"template_id": tpl.id, "name": tpl.name, "prompt": tpl.prompt}


@router.delete("/templates/{tpl_id}")
def delete_template(tpl_id: int, request: Request,
                    session: Session = Depends(get_session)) -> dict:
    uid = _current_user(request, session)
    tpl = _get_own(session, tpl_id, uid)
    session.delete(tpl)
    session.commit()
    return {"deleted": tpl_id}
