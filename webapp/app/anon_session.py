"""Anonyme Session-Identität (Task B3) — Cookie-gebundene anon-User.

Sliding-Retention: ``last_seen_at`` wird höchstens alle 60 s in der DB
aktualisiert (kein Write pro Request); zusätzlich schreibt diese Funktion bei
JEDEM Aufruf einen Timestamp in die Session — Starlette setzt das
Session-Cookie nur neu, wenn sich die Session ändert, und genau dadurch ist
das Cookie-Sliding (max_age = Anon-Retention ab letzter Aktivität) garantiert.
"""
from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone

from sqlmodel import Session

from .anon_names import generate_name
from .config import settings
from .models import User


def current_uid(request, session=None):
    """User-ID für den aktuellen Request — erzeugt anonyme Sessions.

    Mit ``session`` (DB-Session) ist die ID immer gesetzt: OIDC-User bei
    eingeloggter Session, sonst Cookie-gebundener anon-User (Teil B).
    """
    if session is not None:
        return ensure_anonymous_user(session, request).id
    if not settings.OIDC_ENABLED:
        return None
    return request.session.get("user_id")


def ensure_anonymous_user(session: Session, request) -> User:
    """Return the current user; creates an anonymous one on first visit."""
    if settings.OIDC_ENABLED and request.session.get("user_id"):
        return session.get(User, request.session["user_id"])  # OIDC-User (kind=oidc)
    anon_id = request.session.get("anon_user_id")
    user = session.get(User, int(anon_id)) if anon_id else None
    if not user or user.kind != "anonymous":
        user = User(sub=f"anon:{uuid.uuid4().hex}", kind="anonymous",
                    display_name=generate_name())
        session.add(user)
        session.commit()
        session.refresh(user)
        request.session["anon_user_id"] = user.id
    now = datetime.now(timezone.utc)
    last = user.last_seen_at
    if last is not None and last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)  # SQLite liefert naive datetimes
    if last is None or (now - last).total_seconds() > 60:
        user.last_seen_at = now
        session.add(user)
        session.commit()
    request.session["last_seen"] = int(time.time())  # Cookie-Sliding
    return user
