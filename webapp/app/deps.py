"""FastAPI dependencies — admin gate + authenticated-user gate.

``require_admin`` guards every /api/admin route. Admin status is derived at
login (POLYSCHNACK_ADMINS / OIDC groups, see routers/auth.py) and cached in
the session. When OIDC is disabled there is no admin area at all.

``require_authenticated`` guards per-user settings (Templates/Targets/BYOK):
only OIDC users pass, anonymous sessions get 403. Like the admin gate it is
disabled when OIDC is off (dev/test mode) — the gate protects the OIDC prod.
"""
from __future__ import annotations

from fastapi import Depends, HTTPException, Request
from sqlmodel import Session

from .config import settings
from .db import get_session
from .identity import current_identity


def require_admin(request: Request) -> None:
    """403 unless the session belongs to an admin; disabled when OIDC is off."""
    if not settings.OIDC_ENABLED:
        raise HTTPException(403, "admin area disabled (OIDC not configured)")
    if not request.session.get("is_admin"):
        raise HTTPException(403, "admin required")


def require_authenticated(request: Request,
                          session: Session = Depends(get_session)):
    """OIDC-Session erforderlich (anon-User -> 403).

    Disabled when OIDC is off (dev/test). When OIDC is on, an anonymous
    session (kind="anonymous") is rejected — only kind="oidc" passes.
    """
    if not settings.OIDC_ENABLED:
        return  # Dev/Test: kein Gating
    ident = current_identity(request, session)
    if ident.user.kind != "oidc":
        raise HTTPException(status_code=403, detail="login required")
    return ident
