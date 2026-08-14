# OIDC Login + Per-User Workspaces Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Add optional OpenID Connect (OIDC) login so users get isolated workspaces — each authenticated user sees only their own uploaded files. When OIDC is not configured the app runs in shared (current) mode with no auth.

**Architecture:** FastAPI backend with `authlib` for OIDC flow + JWT session cookie. SQLModel `User` table linked to `Recording` via `user_id` foreign key. Frontend shows login button in header when OIDC is enabled; auto-redirects to IdP; shows user info + logout after auth. All recording queries are scoped to `current_user.id`. The ASR service (`approach-a`) is **not** touched — auth lives entirely in the webapp layer.

**Tech Stack:** Python 3.12+, `authlib>=1.3` + `httpx` for OIDC, `itsdangerous` for session cookies (stdlib-friendly), React/TypeScript frontend. OIDC provider: `auth.example.org` (existing IdP setup). SQLite — no need for Postgres for single-node deployment.

**Current state:** Single `Recording` table, no user concept. All queries return all rows. Frontend has no auth. Compose.yml exposes webapp on port 8088 directly.

**OIDC provider context:** `auth.example.org` is already configured. Same flow: `authorization_endpoint`, `token_endpoint`, `userinfo_endpoint`, client credentials via env vars.

---
## Task 1: Add auth dependencies + config

**Objective:** Add `authlib` and `itsdangerous` to pyproject.toml. Add OIDC config fields to `config.py`.

**Files:**
- Modify: `webapp/pyproject.toml`
- Modify: `webapp/app/config.py`

**Step 1: Add dependencies**

```toml
dependencies = [
    # ...existing...
    "authlib>=1.3",
    "itsdangerous>=2.2",
]
```

**Step 2: Add OIDC config to `_Settings`**

```python
# OIDC (optional — when unset the app runs without auth)
OIDC_CLIENT_ID: str = os.getenv("OIDC_CLIENT_ID", "")
OIDC_CLIENT_SECRET: str = os.getenv("OIDC_CLIENT_SECRET", "")
OIDC_ISSUER: str = os.getenv("OIDC_ISSUER", "")
OIDC_SCOPE: str = os.getenv("OIDC_SCOPE", "openid profile email")
# Session secret — auto-generated if not set (persists in DB). For Docker, set a fixed one.
SESSION_SECRET: str = os.getenv("SESSION_SECRET", "")
OIDC_ENABLED: bool = field(default=False)
```

Add a `__post_init__` or property that sets `OIDC_ENABLED = bool(OIDC_CLIENT_ID and OIDC_CLIENT_SECRET and OIDC_ISSUER)`.

**Step 3: Commit**

```bash
git add webapp/pyproject.toml webapp/app/config.py
git commit -m "feat: add authlib + OIDC config fields"
```

---
## Task 2: Create User model + link Recording

**Objective:** Add a `User` SQLModel table and a `user_id` foreign key on `Recording`. Add `enable_vad`/`enable_diarize` fields if not already there (check first).

**Files:**
- Modify: `webapp/app/models.py`
- Modify: `webapp/app/db.py` (register User model)

**Step 1: Add User model**

```python
class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    sub: str = Field(unique=True, index=True)      # OIDC subject claim
    preferred_username: Optional[str] = None
    email: Optional[str] = None
    name: Optional[str] = None
    created_at: dt.datetime = Field(
        default_factory=lambda: dt.datetime.now(dt.timezone.utc)
    )
```

**Step 2: Add user_id to Recording**

```python
class Recording(SQLModel, table=True):
    # ...existing fields...
    user_id: Optional[int] = Field(default=None, foreign_key="user.id", index=True)
```

Keep `user_id` nullable: `None` = legacy records or unauthenticated mode.

**Step 3: Register User in db.py**

In `db.py`, add `from .models import User as _User` alongside the existing Recording import.

**Step 4: Check DB migration**

Since SQLite + SQLModel + `create_all` handles new tables and nullable columns, just restarting the app is enough. Existing data is preserved (user_id will be NULL for legacy rows).

**Step 5: Commit**

```bash
git add webapp/app/models.py webapp/app/db.py
git commit -m "feat: add User model + user_id foreign key on Recording"
```

---
## Task 3: Create auth router (login/logout/callback/userinfo)

**Objective:** Implement OIDC login flow using `authlib`. Use `httpx` for token/ userinfo requests (authlib handles the OIDC metadata discovery).

**Files:**
- Create: `webapp/app/routers/auth.py`

**Step 1: Write auth.py**

```python
"""OIDC authentication router.

Endpoints:
  GET  /auth/login      → redirect to IdP
  GET  /auth/callback   → OIDC callback, sets session cookie, redirects to /
  GET  /auth/logout     → clears session, redirects to /
  GET  /auth/me         → returns current user info (or 401)

When OIDC is not configured, /auth/me returns {"anonymous": True}
and login/logout return 404.
"""

from __future__ import annotations
import json
import logging
import secrets
from typing import Any, Dict, Optional

import httpx
from authlib.integrations.base_client import OAuthError
from authlib.integrations.httpx_client import OAuthClient
from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import RedirectResponse

from ..config import settings
from ..crud import get_or_create_user
from ..db import get_session

router = APIRouter(prefix="/auth")
log = logging.getLogger(__name__)

# In-memory nonce store (fine for single-process; use Redis for multi-worker)
_nonce_store: Dict[str, str] = {}

if not settings.OIDC_ENABLED:
    @router.get("/login")
    async def login_disabled():
        raise HTTPException(404, "OIDC not configured")

    @router.get("/callback")
    async def callback_disabled():
        raise HTTPException(404, "OIDC not configured")
    
    @router.get("/logout")
    async def logout_disabled():
        raise HTTPException(404, "OIDC not configured")

else:
    _OAUTH = OAuthClient(
        client_id=settings.OIDC_CLIENT_ID,
        client_secret=settings.OIDC_CLIENT_SECRET,
        scope=settings.OIDC_SCOPE,
    )

    @router.get("/login")
    async def login(request: Request):
        # Discover OIDC metadata
        issuer = settings.OIDC_ISSUER
        disco = httpx.get(f"{issuer}/.well-known/openid-configuration").json()
        auth_url = disco["authorization_endpoint"]
        token_url = disco["token_endpoint"]

        state = secrets.token_urlsafe(32)
        nonce = secrets.token_urlsafe(16)
        _nonce_store[state] = nonce
        request.session["oauth_state"] = state  # requires SessionMiddleware

        redirect = _OAUTH.create_authorization_url(
            auth_url,
            state=state,
            nonce=nonce,
            redirect_uri=f"{settings.BASE_URL}/auth/callback",
        )
        return RedirectResponse(redirect)

    @router.get("/callback")
    async def callback(request: Request, code: str, state: str):
        expected_state = request.session.get("oauth_state")
        if not expected_state or expected_state != state:
            raise HTTPException(400, "state mismatch")

        nonce = _nonce_store.pop(state, None)
        if not nonce:
            raise HTTPException(400, "nonce not found")

        issuer = settings.OIDC_ISSUER
        disco = httpx.get(f"{issuer}/.well-known/openid-configuration").json()
        token_url = disco["token_endpoint"]

        token = _OAUTH.fetch_token(
            token_url,
            code=code,
            redirect_uri=f"{settings.BASE_URL}/auth/callback",
        )

        # Fetch userinfo
        userinfo_resp = httpx.get(
            disco["userinfo_endpoint"],
            headers={"Authorization": f"Bearer {token['access_token']}"},
        )
        userinfo_resp.raise_for_status()
        userinfo = userinfo_resp.json()

        # Upsert user in DB
        with next(get_session()) as session:
            user = get_or_create_user(
                session,
                sub=userinfo["sub"],
                preferred_username=userinfo.get("preferred_username"),
                email=userinfo.get("email"),
                name=userinfo.get("name"),
            )
            session.commit()

        # Set session cookie with user ID
        request.session["user_id"] = user.id

        return RedirectResponse("/")

    @router.get("/logout")
    async def logout(request: Request):
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
```

**Key design decisions:**
- `authlib` `OAuthClient` for the OIDC flow (handles token exchange, nonce validation)
- `httpx` for discovery + userinfo (authlib's OAuthClient does token fetch)
- Session stored in signed cookie via `itsdangerous` / FastAPI SessionMiddleware
- `_nonce_store` is in-memory (fine for single-worker; warn in Caddy note)
- No database session tokens — just store `user_id` in cookie

**Step 2: Add `BASE_URL` to config**

In `config.py`, add:
```python
BASE_URL: str = os.getenv("BASE_URL", "http://localhost:8088").rstrip("/")
```

**Step 3: Add FastAPI SessionMiddleware to main.py**

In `main.py`, add session middleware:
```python
from starlette.middleware.sessions import SessionMiddleware
from .config import settings

app = FastAPI(...)
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.SESSION_SECRET or secrets.token_urlsafe(32),
    max_age=86400 * 7,  # 7 days
)
```

**Step 4: Register the auth router**

```python
from .routers.auth import router as auth_router
app.include_router(auth_router)
```

**Step 5: Commit**

```bash
git add webapp/app/routers/auth.py webapp/app/config.py webapp/app/main.py
git commit -m "feat: add OIDC auth router with login/logout/callback/userinfo"
```

---
## Task 4: Add user CRUD helpers

**Objective:** Add `get_or_create_user()`, `get_user()`, and scope `list_recordings()` by `user_id`.

**Files:**
- Modify: `webapp/app/crud.py`

**Step 1: Add user helpers**

```python
def get_or_create_user(
    session: Session,
    *,
    sub: str,
    preferred_username: Optional[str] = None,
    email: Optional[str] = None,
    name: Optional[str] = None,
) -> User:
    user = session.exec(select(User).where(User.sub == sub)).first()
    if user:
        # Update fields that may have changed
        if preferred_username:
            user.preferred_username = preferred_username
        if email:
            user.email = email
        if name:
            user.name = name
        session.add(user)
        return user
    user = User(
        sub=sub,
        preferred_username=preferred_username,
        email=email,
        name=name,
    )
    session.add(user)
    session.flush()
    return user


def get_user(session: Session, user_id: int) -> Optional[User]:
    return session.get(User, user_id)
```

**Step 2: Scope recordings by user**

Add an optional `user_id` filter to `list_recordings`:

```python
def list_recordings(
    session: Session,
    q: Optional[str] = None,
    user_id: Optional[int] = None,
) -> List[Recording]:
    stmt = select(Recording)
    if user_id is not None:
        stmt = stmt.where(Recording.user_id == user_id)
    if q:
        term = f"%{q.lower()}%"
        stmt = stmt.where(
            Recording.original_name.ilike(term) | Recording.text.ilike(term)
        )
    stmt = stmt.order_by(Recording.id.desc())
    return list(session.exec(stmt).all())
```

Similarly add `get_stats` with `user_id` filter.

**Step 3: Pass user_id on recording creation**

In `create_recording`, accept optional `user_id`:

```python
def create_recording(session, ..., user_id: Optional[int] = None) -> Recording:
    rec = Recording(..., user_id=user_id)
```

**Step 4: Commit**

```bash
git add webapp/app/crud.py
git commit -m "feat: add user CRUD + scope recording queries by user_id"
```

---
## Task 5: Wire auth into API endpoints

**Objective:** The recordings router extracts `user_id` from session and scopes all queries. Upload stores `user_id` on the recording.

**Files:**
- Modify: `webapp/app/routers/recordings.py`

**Step 1: Add helper to get current user**

```python
from ..crud import get_user

def _current_user(request: Request) -> Optional[int]:
    """Return current user_id from session, or None if OIDC is disabled."""
    if not settings.OIDC_ENABLED:
        return None
    return request.session.get("user_id")
```

**Step 2: Scope list + get endpoints**

```python
@router.get("/recordings")
def list_recordings_endpoint(
    q: Optional[str] = None,
    request: Request = None,
    session: Session = Depends(get_session),
):
    user_id = _current_user(request)
    rows = list_recordings(session, q=q, user_id=user_id)
    return [_recording_to_dict(r) for r in rows]
```

**Step 3: Assign user_id on upload**

```python
rec = create_recording(
    session,
    ...,
    user_id=_current_user(request),
)
```

**Step 4: Scope stats**

```python
@router.get("/stats")
def stats_endpoint(
    request: Request = None,
    session: Session = Depends(get_session),
):
    user_id = _current_user(request)
    return get_stats(session, user_id=user_id)
```

**Step 5: Commit**

```bash
git add webapp/app/routers/recordings.py
git commit -m "feat: scope recording endpoints by current user"
```

---
## Task 6: Frontend — login button + user info in header

**Objective:** Show a login button / user avatar + logout in the header. Fetch `/auth/me` on page load.

**Files:**
- Modify: `webapp/frontend/src/api.ts`
- Modify: `webapp/frontend/src/App.tsx`

**Step 1: Add auth types + fetch to api.ts**

```typescript
export interface UserInfo {
  anonymous?: boolean;
  authenticated?: boolean;
  sub?: string;
  name?: string;
  preferred_username?: string;
}

export async function fetchMe(): Promise<UserInfo> {
  const res = await fetch("/auth/me");
  return res.json() as Promise<UserInfo>;
}

export async function logout(): Promise<void> {
  window.location.href = "/auth/logout";
}
```

**Step 2: Show login/logout in App header**

In `App.tsx`, add state for user info, fetch on mount, and render:

```tsx
const [user, setUser] = useState<UserInfo | null>(null);

useEffect(() => {
  fetchMe().then(setUser).catch(() => setUser({ anonymous: true }));
}, []);

// In header, after the brand:
{user && !user.anonymous && !user.authenticated && settings?.oidc_enabled && (
  <a href="/auth/login" className="btn-ghost-sm text-[12px]">
    Login
  </a>
)}
{user?.authenticated && (
  <div className="flex items-center gap-2">
    <span className="text-[12px] text-muted">{user.name}</span>
    <button onClick={logout} className="btn-ghost-sm text-[12px]">
      Logout
    </button>
  </div>
)}
```

Add `oidc_enabled` to a new settings endpoint or just check if `/auth/login` returns 200. Simpler: add `GET /api/settings` returning `{oidc_enabled: bool}`.

**Step 3: Create GET /api/settings endpoint**

In a new file or in `main.py`:

```python
@router.get("/api/settings")
def app_settings():
    return {"oidc_enabled": settings.OIDC_ENABLED}
```

**Step 4: Commit**

```bash
git add webapp/frontend/src/api.ts webapp/frontend/src/App.tsx
git commit -m "feat: add login button + user info in header"
```

---
## Task 7: Add OIDC env vars to compose.yml

**Objective:** Document the OIDC configuration in `compose.yml` so users can opt in.

**Files:**
- Modify: `compose.yml`

**Step 1: Add OIDC env vars**

```yaml
  webapp:
    environment:
      # ...existing...
      # Optional OIDC — uncomment to enable per-user workspaces
      # OIDC_CLIENT_ID: ""
      # OIDC_CLIENT_SECRET: ""
      # OIDC_ISSUER: "https://auth.example.org"
      # OIDC_SCOPE: "openid profile email"
      # SESSION_SECRET: "generate-a-random-secret-here"
      # BASE_URL: "https://polyschnack.example.org"
```

**Step 2: Commit**

```bash
git add compose.yml
git commit -m "docs: add OIDC env vars to compose.yml"
```

---
## Verification

1. **Without OIDC:** App starts as before — no login, all recordings shared
2. **With OIDC:** Set env vars → restart → login button appears → redirects to the IdP → callback → user sees empty workspace → upload → logout → different user sees different recordings
3. **Legacy data:** Recordings without `user_id` are invisible to all authenticated users. Optional migration task (Task 10) to assign them.
4. **Stats:** Scoped per user — "5 Aufnahmen" shows only current user's count

---
## Risks & Tradeoffs

| Risk | Mitigation |
|------|------------|
| `_nonce_store` in-memory lost on restart | Nonce expires after a few minutes — user just re-logs in |
| Session cookie not signed | `SessionMiddleware` with `secret_key` signs the cookie |
| OIDC provider down | Auth simply fails — app still works without auth config |
| Auth bypass via direct API calls | All API routes check `_current_user`. Unauthenticated users get empty results (or 401 for mutations) |
| Multi-worker nonce race | Single worker is fine. For scale, move nonce to DB/Redis — YAGNI for now |
| Legacy recordings invisible after migration | Optional "claim recordings" endpoint (Task 10) |

---
## Open Questions

1. Should anonymous (no-OIDC) mode be completely separate (same as current) or should it have a guest user? → **Keep as-is**: no OIDC = shared workspace, no auth at all
2. Admin user? → **YAGNI** for now. Everyone who can log in sees only their own data.
3. What if two IdPs? → **YAGNI**. One OIDC provider is enough.
4. Cookie domain for reverse proxy? → Document that `BASE_URL` must match the external URL for OIDC redirects to work.

---
## Future (not in MVP)

- **Claim legacy recordings** — POST endpoint to assign unclaimed recordings to current user (by `batch_id`, `source`, or filename pattern)
- **Admin panel** — list users, view all recordings
- **API tokens** — personal access tokens for programmatic use
- **Rate limiting** — per-user upload quotas
