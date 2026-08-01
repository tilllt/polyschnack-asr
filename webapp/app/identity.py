"""Identitäts-Auflösung (Task C3) — Bearer-API-Key oder Session/anonym.

Ein API-Key authentifiziert als Identität des Erstellers mit Rechte-Deckel
(``key_level``): die Routen sehen alles, was der Ersteller darf, aber nie mehr
als das Key-Level (Cap in ``permissions.get_access_level``).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from fastapi import HTTPException
from sqlmodel import Session, select

from .anon_session import ensure_anonymous_user
from .models import ApiKey, User, hash_token


@dataclass
class Identity:
    user: object
    key_level: Optional[str] = None  # Rechte-Deckel aus API-Key (None = Session)


def current_identity(request, session: Session) -> Identity:
    auth = request.headers.get("Authorization", "") if hasattr(request, "headers") else ""
    if auth.startswith("Bearer "):
        token = auth[7:].strip()
        if not token:
            raise HTTPException(status_code=401, detail="invalid API key")
        key = session.exec(
            select(ApiKey).where(ApiKey.token_hash == hash_token(token))
        ).first()
        if not key:
            raise HTTPException(status_code=401, detail="invalid API key")
        user = session.get(User, key.user_id)
        if user is None:
            raise HTTPException(status_code=401, detail="invalid API key")
        key.last_used_at = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
        session.add(key)
        session.commit()
        return Identity(user, key.level)
    user = ensure_anonymous_user(session, request)
    return Identity(user, None)
