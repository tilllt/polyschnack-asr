"""Yjs-Kollaboration (Change 053) — Paket: Rooms, Auth-Hook, ASGI-Mount."""
from __future__ import annotations

import base64
import json
import logging

from itsdangerous import BadSignature, SignatureExpired, TimestampSigner

from .rooms import build_asgi_server

log = logging.getLogger(__name__)

SESSION_MAX_AGE = 86400 * 7


def decode_session_cookie(cookie_value: str, secret: str) -> dict | None:
    """Starlette-Session-Cookie dekodieren (aktuelle Starlette: TimestampSigner
    + base64(json); identische Parameter wie SessionMiddleware)."""
    signer = TimestampSigner(str(secret))
    try:
        data = signer.unsign(cookie_value.encode("utf-8"), max_age=SESSION_MAX_AGE)
        return json.loads(base64.b64decode(data))
    except (BadSignature, SignatureExpired):
        return None


def _extract_cookie(scope: dict) -> str:
    headers = dict(scope.get("headers") or [])
    raw = headers.get(b"cookie", b"")
    for part in raw.decode("latin-1", "replace").split(";"):
        name, _, value = part.strip().partition("=")
        if name == "session":
            return value
    return ""


def make_on_connect(secret: str, require_oidc: bool = True):
    """Auth-Hook für ASGIServer: True = Verbindung NICHT akzeptieren.

    Zwei Stufen, konsistent zur Segment-Edit-Route (PUT/PATCH /segments):
    1. Gültige Session mit eingeloggtem User (user_id in der Session) —
       anonyme Sessions (Shared Space) haben keinen Zugriff.
    2. write-Zugriff auf die konkrete Recording (Owner oder per Share
       freigegeben) — die UID steckt im WS-Pfad (/yjs/<recordingUid>).
    """
    def on_connect(msg, scope) -> bool:
        session_data = decode_session_cookie(_extract_cookie(scope), secret)
        if not session_data or session_data.get("user_id") is None:
            log.info("yjs: Verbindung ohne gültige Session abgelehnt")
            return True
        uid_str = (scope.get("path") or "").rsplit("/", 1)[-1]
        try:
            from sqlmodel import Session as _DbSession, select

            from ..db import engine
            from ..models import Recording
            from ..permissions import ensure_access

            with _DbSession(engine) as db:
                rec = db.exec(
                    select(Recording).where(Recording.uid == uid_str)
                ).first()
                if rec is None:
                    log.info("yjs: Recording %s nicht gefunden — abgelehnt", uid_str)
                    return True
                ensure_access(db, rec, session_data["user_id"], "write")
        except Exception:
            log.info("yjs: write-Zugriff auf %s verweigert (kein Owner/Share)", uid_str)
            return True
        return False
    return on_connect


def build_yjs_mount(secret: str):
    """ASGI-App für app.mount('/yjs', ...)."""
    return build_asgi_server(on_connect=make_on_connect(secret))
