"""Application factory for the Parakeet PoC UI.

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
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncGenerator, Dict

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from .config import settings
from .db import init_db
from .routers.recordings import router as recordings_router

log = logging.getLogger(__name__)

_STATIC_DIR = Path(__file__).parent / "static"
_SPA_INDEX = _STATIC_DIR / "index.html"

_DEV_HINT_HTML = """\
<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>Parakeet PoC — frontend not built</title></head>
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
    yield


app = FastAPI(title="Parakeet PoC UI", lifespan=lifespan)

# ------------------------------------------------------------------
# API router + health — registered BEFORE the SPA mount so /api/*
# and /health are never swallowed by the static file handler.
# ------------------------------------------------------------------

app.include_router(recordings_router)


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
