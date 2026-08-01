"""FastAPI dependencies — admin gate.

``require_admin`` guards every /api/admin route. Admin status is derived at
login (POLYSCHNACK_ADMINS / OIDC groups, see routers/auth.py) and cached in
the session. When OIDC is disabled there is no admin area at all.
"""
from __future__ import annotations

from fastapi import HTTPException, Request

from .config import settings


def require_admin(request: Request) -> None:
    """403 unless the session belongs to an admin; disabled when OIDC is off."""
    if not settings.OIDC_ENABLED:
        raise HTTPException(403, "admin area disabled (OIDC not configured)")
    if not request.session.get("is_admin"):
        raise HTTPException(403, "admin required")
