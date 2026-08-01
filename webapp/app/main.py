"""Application factory for the PolySchnack Web UI.

Responsibilities:
  - create the FastAPI instance
  - run ``init_db()`` during lifespan startup
  - include all routers
  - serve ``/health``
  - mount the built React SPA from ``app/static/``; fall back gracefully when
    the static build is absent (e.g. plain dev without ``npm run build``).
"""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncGenerator, Dict

import secrets

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from .config import settings
from .db import init_db
from .routers.recordings import router as recordings_router
from .routers.models import router as models_router, _hf_token, _check_vad, _check_diarize
from .routers.matrix import router as matrix_router
from .routers.auth import router as auth_router
from .routers.segments import router as segments_router
from .routers.url_import import router as url_import_router

log = logging.getLogger(__name__)

_STATIC_DIR = Path(__file__).parent / "static"
_SPA_INDEX = _STATIC_DIR / "index.html"

_DEV_HINT_HTML = """\
<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>PolySchnack — frontend not built</title></head>
<body>
<h1>Frontend not built</h1>
<p>
  Run <code>npm run build</code> inside <code>webapp/frontend/</code>, or use the
  Docker image which bundles the build automatically.<br>
  In local dev, start the Vite dev server on
  <a href="http://localhost:5173">http://localhost:5173</a> and point it at this
  backend.
</p>
<p>The API is still fully available at <code>/api/…</code> and the health check
at <code>/health</code>.</p>
</body>
</html>
"""


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Initialise the database (tables + audio dir) before handling requests."""
    init_db()
    # Ensure the static directory exists so the StaticFiles mount never errors.
    _STATIC_DIR.mkdir(parents=True, exist_ok=True)

    # --- Task 6: start the queue and re-enqueue jobs that were still queued
    # --- when the previous process exited.
    from . import crud
    from .db import engine
    from .queue import QueueError, queue_manager
    from sqlmodel import Session

    queue_manager.start()
    with Session(engine) as session:
        for rec_id, backend, user_id in crud.list_queued(session):
            try:
                queue_manager.enqueue(rec_id, user_id, backend)
            except QueueError:
                log.warning("re-enqueue skipped for rec_id=%s", rec_id)

    # Startup diagnostics: model availability
    hf_token_ok = bool(os.getenv("HF_TOKEN"))
    log.info("HF_TOKEN: %s", "✓ set" if hf_token_ok else "✗ NOT SET — diarization disabled")
    log.info("silero-vad (VAD): %s", "✓ cached" if _check_vad() else "✗ not installed")
    if hf_token_ok:
        log.info("pyannote (diarize): %s", "✓ cached" if _check_diarize() else "✗ not installed — click toggle to download")
    else:
        log.info("pyannote (diarize): skipped (no HF_TOKEN)")

    yield

    queue_manager.stop()


app = FastAPI(title="PolySchnack Web UI", lifespan=lifespan)

# Session middleware (for OIDC auth)
# httponly + same_site=lax are the hard-coded defaults in Starlette >=0.40;
# secure → https_only is the only moved knob.
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.SESSION_SECRET or secrets.token_urlsafe(32),
    max_age=86400 * 7,
    https_only=settings.BASE_URL.startswith("https"),
)

# ------------------------------------------------------------------
# API router + health — registered BEFORE the SPA mount so /api/*
# and /health are never swallowed by the static file handler.
# ------------------------------------------------------------------

app.include_router(recordings_router)
app.include_router(models_router)
app.include_router(matrix_router)
app.include_router(segments_router)
app.include_router(url_import_router)
app.include_router(auth_router)


@app.get("/health")
def health() -> Dict[str, Any]:
    """Liveness check — always returns 200 when the server is up."""
    return {"status": "ok", "asr_url": settings.ASR_URL}


# ------------------------------------------------------------------
# SPA mount — added AFTER the API routes.
# If the build output does not exist we serve a small HTML hint at /
# instead of crashing at startup.
# ------------------------------------------------------------------

if _SPA_INDEX.exists():
    # The React build is present → serve it.  ``html=True`` makes StaticFiles
    # fall back to index.html for unknown paths so the client-side router works.
    app.mount("/", StaticFiles(directory=str(_STATIC_DIR), html=True), name="spa")
    log.info("Serving React SPA from %s", _STATIC_DIR)
else:
    # No build yet — serve the hint page at / so the server still starts.
    log.warning(
        "Static SPA not found at %s — serving dev hint page. "
        "Run `npm run build` or use the Docker image.",
        _SPA_INDEX,
    )

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    def _spa_hint() -> str:
        return _DEV_HINT_HTML
