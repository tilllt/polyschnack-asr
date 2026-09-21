"""Change 228 — Vorgabewerte je Nutzer für den Input-Blick.

Je Nutzer genau eine Zeile (``UserDefaults``): gewählte Quelle, gewählte
Optionswerte und je ein Vorgabewert für Nachbearbeitungs-Vorlage,
LLM-Endpunkt und Auslieferungsziel.

Regeln:
- Der Endpunkt ist ein OIDC-Pfad (wie BYOK und Vorlagen) — anonyme Nutzer
  haben keine Vorlagen/Ziele und damit auch keinen Vorgabewert.
- Zeigt ein Feld auf einen Datensatz, wird beim Schreiben geprüft, dass er
  dem Nutzer gehört; fremde IDs führen zu 404 (kein Rückschluss auf fremde
  Datensätze).
- Ein Feld kann gezielt geleert werden: wird der Schlüssel im Rumpf
  mitgeschickt und ist ``null``, wird der Vorgabewert entfernt. Fehlt der
  Schlüssel, bleibt der bisherige Wert stehen.
"""
from __future__ import annotations

import json
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlmodel import Session, select

from ..db import get_session
from ..deps import require_authenticated
from ..models import DeliveryTarget, PromptTemplate, UserDefaults, UserLlmEndpoint

router = APIRouter(prefix="/api", dependencies=[Depends(require_authenticated)])

#: Obergrenze für die Optionswerte (Missbrauchsschutz, nicht Fachlichkeit).
_MAX_OPTIONS_JSON = 20_000


class DefaultsUpdate(BaseModel):
    default_source: Optional[Literal["upload", "record", "url"]] = None
    default_options: Optional[dict] = None
    default_template_id: Optional[int] = None
    default_endpoint_id: Optional[int] = None
    default_target_id: Optional[int] = None


def _current_user(request, session=None) -> Optional[int]:
    from ..identity import current_identity

    return current_identity(request, session).user.id


def _row(session: Session, uid: Optional[int]) -> Optional[UserDefaults]:
    if uid is None:
        return None
    return session.exec(
        select(UserDefaults).where(UserDefaults.user_id == uid)
    ).first()


def _to_dict(row: Optional[UserDefaults]) -> dict:
    opts = None
    if row is not None and row.default_options:
        try:
            opts = json.loads(row.default_options)
        except (TypeError, ValueError):
            opts = None  # defekter Altbestand → wie „nicht gesetzt" behandeln
    return {
        "default_source": row.default_source if row is not None else "upload",
        "default_options": opts,
        "default_template_id": row.default_template_id if row is not None else None,
        "default_endpoint_id": row.default_endpoint_id if row is not None else None,
        "default_target_id": row.default_target_id if row is not None else None,
        "configured": row is not None,
    }


def _own_template(session: Session, tpl_id: int, uid: int) -> None:
    t = session.get(PromptTemplate, tpl_id)
    if t is None or t.user_id != uid:
        raise HTTPException(status_code=404, detail="template not found")


def _own_endpoint(session: Session, ep_id: int, uid: int) -> None:
    ep = session.get(UserLlmEndpoint, ep_id)
    if ep is None or ep.user_id != uid:
        raise HTTPException(status_code=404, detail="llm endpoint not found")


def _own_target(session: Session, target_id: int, uid: int) -> None:
    t = session.get(DeliveryTarget, target_id)
    if t is None or t.user_id != uid:
        raise HTTPException(status_code=404, detail="target not found")


@router.get("/defaults")
def get_defaults(request: Request, session: Session = Depends(get_session)) -> dict:
    """Vorgabewerte des angemeldeten Nutzers (nie 404 — fehlend = Standard)."""
    return _to_dict(_row(session, _current_user(request, session)))


@router.put("/defaults")
def put_defaults(body: DefaultsUpdate, request: Request,
                 session: Session = Depends(get_session)) -> dict:
    uid = _current_user(request, session)
    if uid is None:
        raise HTTPException(status_code=403, detail="login required")
    fields = body.model_fields_set
    row = _row(session, uid)
    if row is None:
        row = UserDefaults(user_id=uid)

    if "default_source" in fields and body.default_source is not None:
        row.default_source = body.default_source

    if "default_options" in fields:
        if body.default_options is None:
            row.default_options = None
        else:
            blob = json.dumps(body.default_options, ensure_ascii=False)
            if len(blob) > _MAX_OPTIONS_JSON:
                raise HTTPException(status_code=413, detail="default options too large")
            row.default_options = blob

    if "default_template_id" in fields:
        if body.default_template_id is None:
            row.default_template_id = None
        else:
            _own_template(session, body.default_template_id, uid)
            row.default_template_id = body.default_template_id

    if "default_endpoint_id" in fields:
        if body.default_endpoint_id is None:
            row.default_endpoint_id = None
        else:
            _own_endpoint(session, body.default_endpoint_id, uid)
            row.default_endpoint_id = body.default_endpoint_id

    if "default_target_id" in fields:
        if body.default_target_id is None:
            row.default_target_id = None
        else:
            _own_target(session, body.default_target_id, uid)
            row.default_target_id = body.default_target_id

    import datetime as _dt

    row.updated_at = _dt.datetime.now(_dt.timezone.utc)
    session.add(row)
    session.commit()
    session.refresh(row)
    return _to_dict(row)


@router.delete("/defaults")
def delete_defaults(request: Request,
                    session: Session = Depends(get_session)) -> dict:
    """Alle Vorgabewerte des Nutzers entfernen (Zeile löschen)."""
    uid = _current_user(request, session)
    row = _row(session, uid)
    if row is not None:
        session.delete(row)
        session.commit()
    return _to_dict(None)
