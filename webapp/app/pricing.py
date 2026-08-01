"""Kostenpflichtige Pfade (Task B9/A12/A13).

Quelle der Wahrheit: das Feld ``cost_per_minute_eur`` in der Backend-Definition
(Service-Registry). Anonyme User dürfen keine kostenpflichtigen Backends und
keine LLM-Verarbeitung nutzen — Server-seitig erzwungen (403), Frontend blendet
die Optionen aus.
"""
from __future__ import annotations

from typing import Optional

from fastapi import HTTPException

from .service_registry import get_service


def is_paid_backend(name: str) -> bool:
    svc = get_service(name)
    return bool(svc and (svc.get("cost_per_minute_eur") or 0) > 0)


def paid_route_for(user) -> bool:
    """True, wenn dieser User kostenpflichtige Verarbeitung nutzen darf.

    ``user`` ist ein User-Objekt; None (kein Login) oder kind='anonymous'
    → False.
    """
    if user is None:
        return False
    return getattr(user, "kind", "oidc") != "anonymous"


def ensure_free_only(user, backend: Optional[str] = None,
                     want_llm: bool = False, llm_mode: bool = False) -> None:
    """Ein Enforcer für alle paid-Pfade: Backend-Wahl (B9), LLM-Enhance (A13),
    LLM-Punctuation (A12). Wirft 403, wenn ein anonymer User einen
    kostenpflichtigen Pfad wählt."""
    if paid_route_for(user):
        return
    if (backend and is_paid_backend(backend)) or want_llm or llm_mode:
        raise HTTPException(
            status_code=403,
            detail="kostenpflichtige Endpunkte sind für anonyme Nutzung gesperrt",
        )
