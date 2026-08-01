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
    if user.last_seen_at is None or (now - user.last_seen_at).total_seconds() > 60:
        user.last_seen_at = now
        session.add(user)
        session.commit()
    request.session["last_seen"] = int(time.time())  # Cookie-Sliding
    return user
