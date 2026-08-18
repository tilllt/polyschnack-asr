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
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from .config import settings
from .db import init_db
from .routers.recordings import router as recordings_router
from .routers.recovery import router as recovery_router
from .routers.api_docs import router as api_docs_router
from .routers.openai_proxy import router as openai_proxy_router
from .routers.cancel import router as cancel_router
from .routers.models import router as models_router, _check_vad, _check_diarize
from .routers.matrix import router as matrix_router
from .routers.queue_api import router as queue_api_router
from .routers.admin import router as admin_router
from .routers.auth import router as auth_router
from .routers.benchmark import router as benchmark_router
from .routers.segments import router as segments_router
from .routers.shares import router as shares_router
from .routers.versions import router as versions_router
from .routers.keys import router as keys_router
from .routers.llm_endpoints import router as llm_endpoints_router
from .routers.templates import router as templates_router
from .routers.targets import router as targets_router
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
        from .models import User

        for rec_id, backend, user_id in crud.list_queued(session):
            try:
                user = session.get(User, user_id) if user_id is not None else None
                queue_manager.enqueue(
                    rec_id, user_id, backend,
                    priority=1 if (user is not None and user.kind == "anonymous") else 0,
                )
            except QueueError:
                log.warning("re-enqueue skipped for rec_id=%s", rec_id)

    # Startup diagnostics: model availability
    log.info("silero-vad (VAD): %s", "✓ cached" if _check_vad() else "✗ not installed")
    diar_ok = _check_diarize()
    log.info("diarization (CrispASR-diar): %s", "✓ reachable" if diar_ok else "✗ NOT reachable — container 'diar' prüfen")

    # --- Task B4: Retention-Sweep für anonyme Sessions (alle 5 min) ---
    # Im selben Loop: Stale-Processing-Watchdog (hängende Transkriptionen,
    # z.B. nach Container-OOM oder abgerissener SSE-Verbindung → failed)
    # und Recording-Health-Scan (Change 014: DB-Eintrag ohne gültige Datei
    # → failed, damit die GUI den Defekt zeigt und Delete funktioniert).
    import threading
    from .retention import sweep
    from .stale_jobs import sweep_stale_processing

    _sweep_stop = threading.Event()

    def _sweep_loop():
        interval_s = max(60, settings.POLYSCHNACK_ANON_RETENTION_MINUTES * 60 // 3)
        while not _sweep_stop.wait(interval_s):
            try:
                with Session(engine) as session:
                    n = sweep(session)
                    if n:
                        log.info("retention sweep: %d anon user(s) deleted", n)
                    stale = sweep_stale_processing(session)
                    if stale:
                        log.info("stale sweep: %d hängende Transkription(en) als failed markiert", stale)
                    from .recording_health import run_health_scan

                    broken = run_health_scan(session, settings.AUDIO_DIR)
                    if broken:
                        log.info("health scan: %d Recording(s) ohne gültige Datei als failed markiert", broken)
            except Exception:
                log.exception("retention sweep failed")

    threading.Thread(target=_sweep_loop, daemon=True, name="retention-sweep").start()

    # --- Peaks-Backfill (2026-08-15): fehlende Waveform-Peaks über alle
    # --- User seriell nachberechnen (2 pro Durchlauf, alle 30 s). Ersetzt
    # --- das frühere Feuerwerk bei GET /recordings (Dutzende parallele
    # --- ffmpeg-Decodes → CPU/RAM-Kollaps).
    from .routers.recordings import _backfill_peaks_batch

    _peaks_stop = threading.Event()

    def _peaks_loop():
        while not _peaks_stop.wait(30):
            try:
                n = _backfill_peaks_batch(limit=2)
                if n:
                    log.info("peaks backfill: %d Aufnahme(n) nachgezogen", n)
            except Exception:
                log.exception("peaks backfill failed")

    threading.Thread(target=_peaks_loop, daemon=True, name="peaks-backfill").start()

    yield

    _sweep_stop.set()
    _peaks_stop.set()
    queue_manager.stop()


app = FastAPI(title="PolySchnack Web UI", lifespan=lifespan)

# --------------------------------------------------------------------------
# OpenAPI-Security-Scheme: API-Key als Bearer (Settings → API-Keys). Der
# OpenAI-Proxy verlangt ihn; Swagger-UI zeigt den Authorize-Button. Das
# Scheme wird per custom openapi() ergänzt, weil FastAPI es nicht aus der
# Dependency-Auth ableiten kann.
# --------------------------------------------------------------------------


def _custom_openapi():
    if app.openapi_schema is not None:
        return app.openapi_schema
    schema = _base_openapi()
    schema.setdefault("components", {}).setdefault("securitySchemes", {})[
        "ApiKeyAuth"
    ] = {
        "type": "http",
        "scheme": "bearer",
        "description": (
            "API-Key aus den Einstellungen (Settings → API-Keys). "
            "Wird als 'Authorization: Bearer <key>' übertragen."
        ),
    }
    schema.setdefault("security", [{"ApiKeyAuth": []}])
    # Die Proxy-Operation verlangt den Key explizit (Swagger-Authorize-Button)
    for path in ("/v1/audio/transcriptions",):
        op = schema.get("paths", {}).get(path, {}).get("post")
        if op is not None:
            op.setdefault("security", [{"ApiKeyAuth": []}])
    app.openapi_schema = schema
    return schema


_base_openapi = app.openapi
app.openapi = _custom_openapi

# ------------------------------------------------------------------
# SEO-Schutz: KEINE Seite (inkl. Anon-Share-Links unter /r/:uid) darf
# von Suchmaschinen indiziert werden. X-Robots-Tag auf allen Responses.
# ------------------------------------------------------------------


@app.middleware("http")
async def _noindex_header(request, call_next):
    resp = await call_next(request)
    resp.headers["X-Robots-Tag"] = "noindex, nofollow"
    return resp


_ROBOTS_TXT = "User-agent: *\nDisallow: /\n"


@app.get("/robots.txt", response_class=PlainTextResponse, include_in_schema=False)
def robots_txt() -> str:
    """robots.txt — immer erreichbar, auch ohne SPA-Build (eigene Route)."""
    return _ROBOTS_TXT

# Session middleware (for OIDC auth)
# httponly + same_site=lax are the hard-coded defaults in Starlette >=0.40;
# secure → https_only is the only moved knob.
app.add_middleware(
    SessionMiddleware,
    # Review 2026-08-15 (P1.5): kein Zufalls-Key mehr pro Prozess — das
    # verwaiste bei jedem Restart alle anon-User. settings.SESSION_SECRET
    # ist persistiert (Env oder DATA_DIR/.session_secret).
    secret_key=settings.SESSION_SECRET,
    max_age=86400 * 7,
    https_only=settings.BASE_URL.startswith("https"),
)

# ------------------------------------------------------------------
# API router + health — registered BEFORE the SPA mount so /api/*
# and /health are never swallowed by the static file handler.
# ------------------------------------------------------------------

app.include_router(recordings_router)
app.include_router(recovery_router)
app.include_router(api_docs_router)
app.include_router(openai_proxy_router)
app.include_router(cancel_router)
app.include_router(models_router)
app.include_router(matrix_router)
app.include_router(queue_api_router)
app.include_router(admin_router)
app.include_router(segments_router)
app.include_router(shares_router)
app.include_router(versions_router)
app.include_router(keys_router)
app.include_router(llm_endpoints_router)
app.include_router(templates_router)
app.include_router(targets_router)
app.include_router(url_import_router)
app.include_router(auth_router)
app.include_router(benchmark_router)


@app.get("/health")
def health() -> Dict[str, Any]:
    """Liveness check — always returns 200 when the server is up."""
    return {"status": "ok", "asr_url": settings.ASR_URL}


# ------------------------------------------------------------------
# SPA mount — added AFTER the API routes.
# If the build output does not exist we serve a small HTML hint at /
# instead of crashing at startup.
# ------------------------------------------------------------------

@app.get("/{full_path:path}", include_in_schema=False)
def spa_fallback(full_path: str):
    """Statische Assets servieren; unbekannte Pfade (z.B. /r/:uid
    Share-Links) → index.html, damit der Client-Router rendert.
    API-Pfade ohne Treffer bleiben 404."""
    from fastapi import HTTPException
    from fastapi.responses import FileResponse

    if full_path.startswith("api/"):
        raise HTTPException(status_code=404)
    candidate = _STATIC_DIR / full_path
    if full_path and candidate.is_file():
        return FileResponse(candidate)
    if _SPA_INDEX.exists():
        return FileResponse(_SPA_INDEX)
    if not full_path:
        return HTMLResponse(_DEV_HINT_HTML)
    raise HTTPException(status_code=404)


if _SPA_INDEX.exists():
    log.info("Serving React SPA from %s", _STATIC_DIR)
else:
    log.warning(
        "Static SPA not found at %s — serving dev hint page. "
        "Run `npm run build` or use the Docker image.",
        _SPA_INDEX,
    )
