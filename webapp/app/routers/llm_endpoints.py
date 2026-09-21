"""BYOK-Endpunkt-CRUD (Task E2) — owner-only, Key verschlüsselt, nur OIDC."""
from __future__ import annotations

from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlmodel import Session, select

import httpx

from .. import crypto
from ..config import settings
from ..db import get_session
from ..deps import require_authenticated
from ..llm_url import validate_llm_url
from ..models import User, UserLlmEndpoint

router = APIRouter(prefix="/api/llm-endpoints",
                   dependencies=[Depends(require_authenticated)])


class EndpointCreate(BaseModel):
    name: str
    base_url: str
    api_key: str
    model: str = "deepseek-chat"


class EndpointUpdate(BaseModel):
    name: Optional[str] = None
    base_url: Optional[str] = None
    api_key: Optional[str] = None  # leer/None = Key behalten
    model: Optional[str] = None


def _current_user(request, session=None) -> Optional[int]:
    from ..identity import current_identity

    return current_identity(request, session).user.id


def _require_oidc(session: Session, uid: Optional[int]) -> User:
    """BYOK ist ein paid-Pfad → nur registrierte User."""
    user = session.get(User, uid) if uid is not None else None
    if user is None or user.kind != "oidc":
        raise HTTPException(status_code=403, detail="login required (paid path)")
    return user


def _to_dict(ep: UserLlmEndpoint) -> dict:
    return {
        "endpoint_id": ep.id,
        "name": ep.name,
        "base_url": ep.base_url,
        "model": ep.model,
        # api_key wird NIE zurückgegeben
    }


def _get_own(session: Session, ep_id: int, user_id: int) -> UserLlmEndpoint:
    ep = session.get(UserLlmEndpoint, ep_id)
    if ep is None or ep.user_id != user_id:
        raise HTTPException(status_code=404, detail="not found")
    return ep


@router.get("")
def list_endpoints(request: Request, session: Session = Depends(get_session)) -> list:
    uid = _current_user(request, session)
    rows = session.exec(
        select(UserLlmEndpoint).where(UserLlmEndpoint.user_id == uid)
    ).all()
    return [_to_dict(ep) for ep in rows]


@router.post("")
def create_endpoint(body: EndpointCreate, request: Request,
                    session: Session = Depends(get_session)) -> dict:
    uid = _current_user(request, session)
    _require_oidc(session, uid)
    validate_llm_url(body.base_url)
    ep = UserLlmEndpoint(
        user_id=uid,
        name=body.name,
        base_url=body.base_url,
        api_key=crypto.encrypt(body.api_key),
        model=body.model,
    )
    session.add(ep)
    session.commit()
    session.refresh(ep)
    return _to_dict(ep)


@router.put("/{ep_id}")
def update_endpoint(ep_id: int, body: EndpointUpdate, request: Request,
                    session: Session = Depends(get_session)) -> dict:
    uid = _current_user(request, session)
    _require_oidc(session, uid)
    ep = _get_own(session, ep_id, uid)
    if body.name is not None:
        ep.name = body.name
    if body.base_url is not None:
        validate_llm_url(body.base_url)
        ep.base_url = body.base_url
    if body.model is not None:
        ep.model = body.model
    if body.api_key:  # leer/None = alter Key bleibt
        ep.api_key = crypto.encrypt(body.api_key)
    session.add(ep)
    session.commit()
    session.refresh(ep)
    return _to_dict(ep)


@router.delete("/{ep_id}")
def delete_endpoint(ep_id: int, request: Request,
                    session: Session = Depends(get_session)) -> dict:
    uid = _current_user(request, session)
    _require_oidc(session, uid)
    ep = _get_own(session, ep_id, uid)
    session.delete(ep)
    session.commit()
    return {"deleted": ep_id}


# ---------------------------------------------------------------- Change 228
class ModelsQuery(BaseModel):
    """Quelle für die Modellliste.

    ``endpoint_id`` (gespeicherter BYOK-Endpunkt) schlägt im Rumpf
    mitgegebene Werte; ohne beides gelten die Server-Einstellungen
    (``POLYSCHNACK_LLM_*``).
    """

    endpoint_id: Optional[int] = None
    base_url: Optional[str] = None
    api_key: Optional[str] = None


@router.post("/models")
def list_provider_models(body: ModelsQuery, request: Request,
                         session: Session = Depends(get_session)) -> dict:
    """Modellliste des konfigurierten Providers (OpenAI-kompatibel).

    Antwortet IMMER mit ``ok``: bei Fehlern steht Klartext in ``error``, damit
    die Oberfläche es anzeigen kann, statt still leer zu bleiben. Der
    Schlüssel wird nie zurückgegeben.
    """
    uid = _current_user(request, session)
    source = "server"
    if body.endpoint_id is not None:
        _require_oidc(session, uid)
        ep = _get_own(session, body.endpoint_id, uid)
        base_url = ep.base_url
        key = crypto.decrypt(ep.api_key) if ep.api_key else ""
        source = "byok"
    elif (body.base_url or "").strip():
        base_url = (body.base_url or "").strip()
        key = (body.api_key or "").strip()
        source = "eingabe"
    else:
        base_url = settings.POLYSCHNACK_LLM_URL
        key = settings.POLYSCHNACK_LLM_API_KEY

    if not base_url:
        return {"ok": False, "models": [], "source": source,
                "error": "kein Provider konfiguriert — Basis-URL fehlt"}

    try:
        validate_llm_url(base_url)
    except Exception as exc:  # Klartext an die Oberfläche, kein stiller Fehler
        return {"ok": False, "models": [], "source": source,
                "error": f"unzulässige Basis-URL: {exc}"}

    url = base_url.rstrip("/") + "/models"
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    try:
        r = httpx.get(url, headers=headers, timeout=15)
        r.raise_for_status()
        payload = r.json()
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "models": [], "source": source, "url": url,
                "error": f"{type(exc).__name__}: {exc}"}

    raw = payload.get("data") if isinstance(payload, dict) else payload
    if raw is None and isinstance(payload, dict):
        raw = payload.get("models")
    models: list[str] = []
    for item in raw or []:
        if isinstance(item, dict):
            mid = item.get("id") or item.get("name")
        else:
            mid = item if isinstance(item, str) else None
        if mid:
            models.append(str(mid))
    models = sorted(set(models))
    return {"ok": True, "models": models, "count": len(models),
            "source": source, "url": url}
