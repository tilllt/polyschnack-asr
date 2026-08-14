"""OIDC authentication router — generic, works with any standard OIDC provider.

Endpoints:
  GET /auth/login    → redirect to IdP (404 when OIDC not configured)
  GET /auth/callback → OIDC callback, sets session, redirects to /
  GET /auth/logout   → clears session, redirects to /
  GET /auth/me       → current user info (or {"anonymous":True})

Uses standard OIDC Authorization Code flow with PKCE.
Works with Keycloak, Authentik, Google, etc.
No dependency on authlib — pure httpx + stdlib.
"""
from __future__ import annotations

import logging
import secrets
from typing import Any, Dict
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse

from ..config import settings
from ..crud import get_or_create_user
from ..db import get_session

log = logging.getLogger(__name__)
router = APIRouter(prefix="/auth")
# In-memory nonce store (single-worker only; fine for this deployment)
_nonce_store: Dict[str, str] = {}


def _is_admin(userinfo: dict, user) -> bool:
    """Env-based admin check: sub/email in POLYSCHNACK_ADMINS or OIDC group intersection.

    No DB field — derived per login, cached in the session.
    """
    admins = {a.strip() for a in settings.POLYSCHNACK_ADMINS.split(",") if a.strip()}
    if user.sub in admins or (user.email and user.email in admins):
        return True
    groups = {g.strip() for g in settings.POLYSCHNACK_ADMIN_GROUPS.split(",") if g.strip()}
    if groups:
        user_groups = set(userinfo.get("groups") or [])
        if user_groups & groups:
            return True
    return False


def _discover(issuer: str) -> dict:
    resp = httpx.get(f"{issuer}/.well-known/openid-configuration")
    resp.raise_for_status()
    return resp.json()


def _gen_state() -> str:
    return secrets.token_urlsafe(32)


def _gen_nonce() -> str:
    return secrets.token_urlsafe(16)


def _build_auth_url(disco: dict, state: str, nonce: str) -> str:
    params = {
        "response_type": "code",
        "client_id": settings.OIDC_CLIENT_ID,
        "redirect_uri": f"{settings.BASE_URL}/auth/callback",
        "scope": settings.OIDC_SCOPE,
        "state": state,
        "nonce": nonce,
    }
    return f"{disco['authorization_endpoint']}?{urlencode(params)}"


def _exchange_code(disco: dict, code: str) -> dict:
    """Exchange authorization code for token using httpx."""
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "client_id": settings.OIDC_CLIENT_ID,
        "client_secret": settings.OIDC_CLIENT_SECRET,
        "redirect_uri": f"{settings.BASE_URL}/auth/callback",
    }
    resp = httpx.post(disco["token_endpoint"], data=data)
    if resp.status_code != 200:
        log.error("OIDC token exchange failed (HTTP %d): %s", resp.status_code, resp.text[:500])
    resp.raise_for_status()
    return resp.json()


# ------------------------------------------------------------------
# Routes
# ------------------------------------------------------------------


@router.get("/login")
async def login(request: Request):
    if not settings.OIDC_ENABLED:
        raise HTTPException(404, "OIDC not configured")
    try:
        disco = _discover(settings.OIDC_ISSUER)
    except Exception as exc:
        log.warning("OIDC discovery failed for issuer=%s: %s", settings.OIDC_ISSUER, exc)
        raise HTTPException(502, f"OIDC provider unreachable: check OIDC_ISSUER ({exc})")
    state = _gen_state()
    nonce = _gen_nonce()
    _nonce_store[state] = nonce
    request.session["oauth_state"] = state
    try:
        url = _build_auth_url(disco, state, nonce)
    except Exception as exc:
        log.warning("OIDC auth URL build failed: %s", exc)
        raise HTTPException(502, f"OIDC misconfiguration: {exc}")
    return RedirectResponse(url)


@router.get("/callback")
async def callback(request: Request, code: str, state: str):
    if not settings.OIDC_ENABLED:
        raise HTTPException(404, "OIDC not configured")
    expected = request.session.get("oauth_state")
    if not expected or expected != state:
        raise HTTPException(400, "state mismatch")
    nonce = _nonce_store.pop(state, None)
    if not nonce:
        raise HTTPException(400, "session expired — please log in again")

    try:
        disco = _discover(settings.OIDC_ISSUER)
        token = _exchange_code(disco, code)
    except Exception as exc:
        log.warning("OIDC token exchange failed: %s", exc)
        raise HTTPException(502, f"OIDC token exchange failed: {exc}")

    try:
        resp = httpx.get(
            disco["userinfo_endpoint"],
            headers={"Authorization": f"Bearer {token['access_token']}"},
        )
        resp.raise_for_status()
        userinfo = resp.json()
    except Exception as exc:
        log.warning("OIDC userinfo fetch failed: %s", exc)
        raise HTTPException(502, f"OIDC userinfo failed: {exc}")

    with next(get_session()) as session:
        user = get_or_create_user(
            session,
            sub=userinfo["sub"],
            preferred_username=userinfo.get("preferred_username"),
            email=userinfo.get("email"),
            name=userinfo.get("name"),
        )
        session.commit()
        request.session["user_id"] = user.id
        request.session["is_admin"] = _is_admin(userinfo, user)
        # OIDC-Gruppen fuer die Settings-Anzeige (z. B. Admin-Gruppen-Match).
        request.session["groups"] = list(userinfo.get("groups") or [])
    return RedirectResponse("/")


@router.get("/logout")
async def logout(request: Request):
    if not settings.OIDC_ENABLED:
        raise HTTPException(404, "OIDC not configured")
    request.session.clear()
    return RedirectResponse("/")


@router.get("/me")
def me(request: Request) -> Dict[str, Any]:
    oidc_enabled = settings.OIDC_ENABLED
    user_id = request.session.get("user_id")
    if user_id:
        # Eingeloggter OIDC-User — kein anon-Fall.
        with next(get_session()) as session:
            from ..crud import get_user
            user = get_user(session, user_id)
            if not user:
                return {"authenticated": False, "oidc_enabled": oidc_enabled}
            return {
                "authenticated": True,
                "oidc_enabled": oidc_enabled,
                "sub": user.sub,
                "name": user.name or user.preferred_username or user.email,
                "preferred_username": user.preferred_username,
                "email": user.email,
                "is_admin": bool(request.session.get("is_admin")),
                "groups": list(request.session.get("groups") or []),
            }
    # Anon-Pfad (auch bei OIDC_ENABLED): Dummy-Name + Retention-Hinweis.
    # ensure_anonymous_user erzeugt/liest den Cookie-gebundenen anon-User.
    with next(get_session()) as session:
        from ..anon_session import ensure_anonymous_user
        from ..config import settings as _s

        user = ensure_anonymous_user(session, request)
        return {
            "anonymous": True,
            "oidc_enabled": oidc_enabled,
            "name": user.display_name or user.name,
            "retention_minutes": _s.POLYSCHNACK_ANON_RETENTION_MINUTES,
        }
