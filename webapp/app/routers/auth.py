"""OIDC authentication router — generic, works with any standard OIDC provider.

Endpoints:
  GET /auth/login    → redirect to IdP (404 when OIDC not configured)
  GET /auth/callback → OIDC callback, sets session, redirects to /
  GET /auth/logout   → clears session, redirects to /
  GET /auth/me       → current user info (or {"anonymous":True})

The implementation uses ``.well-known/openid-configuration`` discovery so it
works with auth.example.com, Keycloak, Authentik, Google, etc.
"""
from __future__ import annotations

import logging
import secrets
from typing import Any, Dict

import httpx
from authlib.integrations.httpx_client import OAuthClient
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse

from ..config import settings
from ..crud import get_or_create_user
from ..db import get_session

log = logging.getLogger(__name__)

router = APIRouter(prefix="/auth")

# In-memory nonce store (single-worker only; fine for this deployment)
_nonce_store: Dict[str, str] = {}


@router.get("/login")
async def login(request: Request):
    if not settings.OIDC_ENABLED:
        raise HTTPException(404, "OIDC not configured")
    issuer = settings.OIDC_ISSUER
    disco = httpx.get(f"{issuer}/.well-known/openid-configuration").json()
    auth_url = disco["authorization_endpoint"]
    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(16)
    _nonce_store[state] = nonce
    request.session["oauth_state"] = state
    oauth = OAuthClient(
        client_id=settings.OIDC_CLIENT_ID,
        client_secret=settings.OIDC_CLIENT_SECRET,
        scope=settings.OIDC_SCOPE,
    )
    redirect = oauth.create_authorization_url(
        auth_url,
        state=state,
        nonce=nonce,
        redirect_uri=f"{settings.BASE_URL}/auth/callback",
    )
    return RedirectResponse(redirect)


@router.get("/callback")
async def callback(request: Request, code: str, state: str):
    if not settings.OIDC_ENABLED:
        raise HTTPException(404, "OIDC not configured")
    expected_state = request.session.get("oauth_state")
    if not expected_state or expected_state != state:
        raise HTTPException(400, "state mismatch")
    nonce = _nonce_store.pop(state, None)
    if not nonce:
        raise HTTPException(400, "nonce not found")
    issuer = settings.OIDC_ISSUER
    disco = httpx.get(f"{issuer}/.well-known/openid-configuration").json()
    token_url = disco["token_endpoint"]
    oauth = OAuthClient(
        client_id=settings.OIDC_CLIENT_ID,
        client_secret=settings.OIDC_CLIENT_SECRET,
        scope=settings.OIDC_SCOPE,
    )
    token = oauth.fetch_token(
        token_url,
        code=code,
        redirect_uri=f"{settings.BASE_URL}/auth/callback",
    )
    # Fetch userinfo
    resp = httpx.get(
        disco["userinfo_endpoint"],
        headers={"Authorization": f"Bearer {token['access_token']}"},
    )
    resp.raise_for_status()
    userinfo = resp.json()
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
    return RedirectResponse("/")


@router.get("/logout")
async def logout(request: Request):
    if not settings.OIDC_ENABLED:
        raise HTTPException(404, "OIDC not configured")
    request.session.clear()
    return RedirectResponse("/")


@router.get("/me")
def me(request: Request) -> Dict[str, Any]:
    if not settings.OIDC_ENABLED:
        return {"anonymous": True}
    user_id = request.session.get("user_id")
    if not user_id:
        return {"authenticated": False}
    with next(get_session()) as session:
        from ..crud import get_user
        user = get_user(session, user_id)
        if not user:
            return {"authenticated": False}
        return {
            "authenticated": True,
            "sub": user.sub,
            "name": user.name or user.preferred_username or user.email,
            "preferred_username": user.preferred_username,
        }
