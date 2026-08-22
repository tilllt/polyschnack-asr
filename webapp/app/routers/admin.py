"""Admin API — service start/stop/restart, backend switch, config (Task 8).

Decisions 7 & 8:
- only admins start/stop services and switch the backend (require_admin on the router)
- an endpoint with active jobs cannot be stopped (409 with count) — jobs finish
- switching to a NOT-running backend is allowed: the service is started
  automatically after the resource check; on insufficient resources the
  switch is rejected (409) and the default stays unchanged.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from .. import app_config
from ..config import settings
from ..db import get_session
from ..deps import require_admin
from ..docker_proxy import DockerProxyClient, DockerProxyError, get_docker_client
from ..queue import QueueError, queue_manager
from ..resources import check_resources
from ..service_registry import get_service, list_services, total_concurrency

router = APIRouter(prefix="/api/admin", dependencies=[Depends(require_admin)])

_HEALTH_WAIT_S = 120
_HEALTH_POLL_S = 2


def _container_name(svc: Dict[str, Any]) -> str:
    """Container-Name = Service-Name (Option C, aus der Registry)."""
    from ..service_registry import container_name as _cn
    return _cn(svc)


def _proxy_error(exc: Exception) -> HTTPException:
    return HTTPException(status_code=503, detail=f"docker-proxy unreachable: {exc}")


# ---------------------------------------------------------------------------
# Service listing
# ---------------------------------------------------------------------------


@router.get("/services")
def admin_services() -> List[Dict[str, Any]]:
    """Registry + live state + resource report + active jobs per service."""
    docker = get_docker_client()
    out: List[Dict[str, Any]] = []
    for svc in list_services():
        container = _container_name(svc)
        try:
            state = docker.container_state(container)
            rep = check_resources(svc, docker)
        except DockerProxyError as exc:
            raise _proxy_error(exc)
        out.append({
            "name": svc["name"],
            "container": container,
            "profile": svc["compose_profile"],
            "model": svc["model"],
            "status": (state or {}).get("status", "not-created"),
            "health": (state or {}).get("health"),
            "resources": {
                "ok": rep.ok,
                "available": rep.available,
                "missing": rep.missing,
                "unknown": rep.unknown,
                "message": rep.message,
            },
            "active_jobs": queue_manager.active_jobs_for(svc["backend"]),
            "concurrency": svc["concurrency"],
        })
    return out


# ---------------------------------------------------------------------------
# Start / stop / restart
# ---------------------------------------------------------------------------


def _start_with_check(svc: Dict[str, Any], docker: DockerProxyClient) -> Dict[str, Any]:
    """Resource check -> docker start -> health wait (Decision 8 sequence)."""
    try:
        rep = check_resources(svc, docker)
    except DockerProxyError as exc:
        raise _proxy_error(exc)
    if not rep.ok:
        raise HTTPException(
            status_code=409,
            detail={
                "reason": "insufficient_resources",
                "message": rep.message,
                "missing": rep.missing,
            },
        )

    container = _container_name(svc)
    try:
        state = docker.container_state(container)
    except DockerProxyError as exc:
        raise _proxy_error(exc)
    if state is None:
        raise HTTPException(
            status_code=409,
            detail={
                "reason": "not_created",
                "message": "Container existiert nicht — Setup einmalig ausführen: "
                           "docker compose --profile crispr-pk-cpp --profile crispr-qwen3 "
                           "--profile crispr-ark --profile ps-voxtral up -d --no-start",
            },
        )
    if state.get("running"):
        raise HTTPException(status_code=409, detail={"reason": "already_running"})

    try:
        docker.start(container)
    except DockerProxyError as exc:
        raise _proxy_error(exc)

    # Health wait: healthy, or running without a healthcheck.
    deadline = time.monotonic() + _HEALTH_WAIT_S
    while time.monotonic() < deadline:
        time.sleep(_HEALTH_POLL_S)
        st = docker.container_state(container)
        if st is None:
            continue
        if st.get("health") == "healthy":
            return {"status": "running", "health": "healthy"}
        if st.get("health") is None and st.get("status") == "running":
            return {"status": "running", "health": None}

    logs = ""
    try:
        logs = docker.logs(container, tail=50)
    except DockerProxyError:
        pass
    raise HTTPException(
        status_code=502,
        detail={
            "reason": "start_timeout",
            "message": "Service wurde gestartet, wurde aber nicht healthy (120 s)",
            "logs": logs[-2000:],
        },
    )


@router.post("/services/{name}/start")
def start_service(name: str, request: Request) -> Dict[str, Any]:
    svc = get_service(name)
    if svc is None:
        raise HTTPException(status_code=404, detail=f"unknown service {name}")
    result = _start_with_check(svc, get_docker_client())
    return {"name": name, **result}


@router.post("/services/{name}/stop")
def stop_service(name: str, request: Request) -> Dict[str, Any]:
    """Stop only when no jobs are queued/processing on this endpoint (Decision 7)."""
    svc = get_service(name)
    if svc is None:
        raise HTTPException(status_code=404, detail=f"unknown service {name}")
    docker = get_docker_client()
    active = queue_manager.active_jobs_for(svc["backend"])
    if active > 0:
        raise HTTPException(
            status_code=409,
            detail={
                "reason": "active_jobs",
                "message": f"{active} Transkriptionen laufen noch auf Backend {svc['backend']}",
            },
        )
    container = _container_name(svc)
    try:
        state = docker.container_state(container)
    except DockerProxyError as exc:
        raise _proxy_error(exc)
    if state is None:
        raise HTTPException(status_code=409, detail={"reason": "not_created"})
    if not state.get("running"):
        raise HTTPException(status_code=409, detail={"reason": "already_stopped"})
    docker.stop(container)
    return {"name": name, "status": "stopped"}


@router.post("/services/{name}/restart")
def restart_service(name: str, request: Request) -> Dict[str, Any]:
    svc = get_service(name)
    if svc is None:
        raise HTTPException(status_code=404, detail=f"unknown service {name}")
    docker = get_docker_client()
    active = queue_manager.active_jobs_for(svc["backend"])
    if active > 0:
        raise HTTPException(
            status_code=409,
            detail={
                "reason": "active_jobs",
                "message": f"{active} Transkriptionen laufen noch auf Backend {svc['backend']}",
            },
        )
    container = _container_name(svc)
    try:
        state = docker.container_state(container)
    except DockerProxyError as exc:
        raise _proxy_error(exc)
    if state is None:
        raise HTTPException(status_code=409, detail={"reason": "not_created"})
    docker.restart(container)
    return {"name": name, "status": "restarted"}


@router.get("/services/{name}/logs")
def service_logs(name: str) -> Dict[str, Any]:
    svc = get_service(name)
    if svc is None:
        raise HTTPException(status_code=404, detail=f"unknown service {name}")
    try:
        logs = get_docker_client().logs(_container_name(svc), tail=200)
    except DockerProxyError as exc:
        raise _proxy_error(exc)
    return {"name": name, "logs": logs[-4000:]}


# ---------------------------------------------------------------------------
# Config: default backend switch (Decision 8)
# ---------------------------------------------------------------------------


class ConfigPut(BaseModel):
    default_backend: str


@router.get("/config")
def admin_config() -> Dict[str, Any]:
    return {
        "default_backend": app_config.effective_backend() or settings.POLYSCHNACK_DEFAULT_BACKEND,
        "effective_backend": app_config.effective_backend() or settings.POLYSCHNACK_DEFAULT_BACKEND,
        "concurrency": total_concurrency(),
        "max_queue_len": settings.POLYSCHNACK_MAX_QUEUE_LEN,
    }


#: Env-konfigurierte Optionen — in der Admin-GUI sichtbar, aber nicht änderbar
#: (nur über die Environment des Containers). Secrets werden maskiert.
_ENV_SETTINGS = [
    ("POLYSCHNACK_DEFAULT_BACKEND", "default_backend"),
    ("POLYSCHNACK_PUNCTUATION_MODE", "punctuation_mode"),
    ("POLYSCHNACK_DEFAULT_PUNCTUATION", "default_punctuation"),
    ("POLYSCHNACK_DEFAULT_LLM_ENHANCE", "default_llm_enhance"),
    ("POLYSCHNACK_ANON_RETENTION_MINUTES", "anon_retention_minutes"),
    ("POLYSCHNACK_ANON_MAX_DURATION_S", "anon_max_duration_s"),
    ("POLYSCHNACK_ANON_MAX_DISK_MB", "anon_max_disk_mb"),
    ("POLYSCHNACK_ANON_MAX_UPLOAD_MB", "anon_max_upload_mb"),
    ("POLYSCHNACK_MAX_QUEUE_LEN", "max_queue_len"),
    ("POLYSCHNACK_LLM_URL", "llm_url"),
    ("POLYSCHNACK_LLM_API_KEY", "llm_api_key"),
    ("POLYSCHNACK_LLM_MODEL", "llm_model"),
    ("POLYSCHNACK_SMTP_HOST", "smtp_host"),
    ("POLYSCHNACK_SMTP_PORT", "smtp_port"),
    ("POLYSCHNACK_SMTP_FROM", "smtp_from"),
]

_MASKED = ("API_KEY", "PASS", "SECRET", "TOKEN")


@router.get("/env-settings")
def env_settings() -> Dict[str, Any]:
    """Env-konfigurierte Optionen (read-only) für die Admin-GUI."""
    out: List[Dict[str, Any]] = []
    for key, label in _ENV_SETTINGS:
        val = getattr(settings, key, "")
        if any(tok in key for tok in _MASKED) and val:
            val = "••••••"  # Secrets nie ausgeben
        out.append({"name": label, "key": key, "value": str(val), "source": "env"})
    return {"settings": out}


@router.put("/config")
def put_config(payload: ConfigPut, request: Request) -> Dict[str, Any]:
    svc = get_service(payload.default_backend)
    if svc is None:
        raise HTTPException(status_code=422, detail=f"unknown backend {payload.default_backend}")

    # Decision 8: switching to a NOT-running backend starts it automatically.
    docker = get_docker_client()
    try:
        state = docker.container_state(_container_name(svc))
    except DockerProxyError as exc:
        raise _proxy_error(exc)
    if state is None:
        raise HTTPException(
            status_code=409,
            detail={
                "reason": "not_created",
                "message": "Backend existiert nicht — zuerst den --no-start-Setup ausführen",
            },
        )
    if not state.get("running"):
        _start_with_check(svc, docker)  # raises 409 on insufficient resources

    app_config.set("default_backend", payload.default_backend)
    return {"default_backend": payload.default_backend}


@router.delete("/config/backend")
def reset_config() -> Dict[str, Any]:
    app_config.delete("default_backend")
    return {"default_backend": settings.POLYSCHNACK_DEFAULT_BACKEND}


# ---------------------------------------------------------------------------
# Wartung: SQLite-VACUUM (Datenschutz — gelöschte Seiten physisch freigeben)
# ---------------------------------------------------------------------------


@router.post("/vacuum")
def admin_vacuum() -> Dict[str, Any]:
    """SQLite-VACUUM — kompaktiert die DB-Datei.

    Gibt den Platz von gelöschten Zeilen (Recordings, Transkript-Versionen,
    Shares) physisch frei, damit die Daten nicht mehr in der DB-Datei
    wiederherstellbar sind. Läuft mit eigener Verbindung und
    busy_timeout=60s, da VACUUM exklusiven Zugriff braucht und nicht in
    einer offenen Transaktion laufen darf.
    """
    import sqlite3

    db_path = Path(settings.DB_PATH)
    before = db_path.stat().st_size if db_path.exists() else 0
    try:
        con = sqlite3.connect(str(db_path), timeout=60)
        try:
            con.execute("PRAGMA busy_timeout=60000")
            con.execute("VACUUM")
        finally:
            con.close()
    except sqlite3.OperationalError as exc:
        raise HTTPException(
            status_code=409,
            detail=f"VACUUM fehlgeschlagen (DB beschäftigt?): {exc}",
        ) from exc
    after = db_path.stat().st_size if db_path.exists() else 0
    return {
        "ok": True,
        "before_bytes": before,
        "after_bytes": after,
        "freed_bytes": max(0, before - after),
    }


@router.post("/self-heal")
def self_heal(dry_run: bool = True,
              session=Depends(get_session)) -> Dict[str, Any]:
    """Self-Healing (Change 023): verwaiste Audio-Dateien aufräumen.

    dry_run=True (Default): nur melden, nichts löschen. Löscht nur
    Dateien älter als min_age_s (3600), auf die KEIN Recording.
    stored_path zeigt (Orphan nach Crash zwischen File-Write und
    DB-Commit oder manuellem DB-Eingriff). Laufende Uploads werden
    nie erfasst (zu jung).
    """
    from ..orphan_sweep import collect_referenced_paths, sweep_orphan_files

    refs = collect_referenced_paths(session)
    removed = sweep_orphan_files(settings.AUDIO_DIR, refs,
                                 min_age_s=3600, dry_run=dry_run)
    return {"dry_run": dry_run, "removed": removed,
            "referenced_files": len(refs)}


# ---------------------------------------------------------------------------
# Change 086: Credits & Monetarisierung (Admin)
# ---------------------------------------------------------------------------

class TopUpRequest(BaseModel):
    """POST /api/admin/credits/topup — virtuelles Guthaben erhöhen."""
    user_id: int
    amount_cents: int
    reason: str = "topup"


class TierRequest(BaseModel):
    """POST /api/admin/credits/tier — Zugangskontrolle free|paid|test."""
    user_id: int
    tier: str


def _admin_user_id(request: Request, session) -> Optional[int]:
    """User-ID des aufrufenden Admins (für created_by); None bei Fehler."""
    try:
        from ..identity import current_identity
        ident = current_identity(request, session)
        return ident.user.id if ident and ident.user else None
    except Exception:
        return None


@router.get("/credits/users")
def credits_users(request: Request,
                  session=Depends(get_session)) -> List[Dict[str, Any]]:
    """Alle User: Guthaben, Tier, Verbrauch (für Admin-GUI)."""
    from sqlmodel import select

    from ..ledger import user_spent_cents
    from ..models import User

    out: List[Dict[str, Any]] = []
    for u in session.exec(select(User).order_by(User.id)).all():
        out.append({
            "user_id": u.id,
            "name": u.name or u.preferred_username or u.display_name,
            "tier": u.tier,
            "credits_cents": u.credits_cents,
            "spent_cents": user_spent_cents(session, u.id),
        })
    return out


@router.post("/credits/topup")
def credits_topup(req: TopUpRequest, request: Request,
                  session=Depends(get_session)) -> Dict[str, Any]:
    """Virtuelles Guthaben erhöhen (TopUp) — Ledger-Buchung append-only."""
    if not 1 <= req.amount_cents <= 1_000_000:
        raise HTTPException(status_code=422,
                            detail="amount_cents muss 1..1.000.000 sein")
    from ..ledger import topup
    from ..models import User

    if session.get(User, req.user_id) is None:
        raise HTTPException(status_code=404, detail="user not found")
    user = topup(session, req.user_id, req.amount_cents,
                 reason=req.reason
                 if req.reason in ("topup", "refund", "signup_bonus")
                 else "topup",
                 created_by=_admin_user_id(request, session))
    return {"ok": True, "user_id": req.user_id,
            "credits_cents": user.credits_cents if user else None}


@router.post("/credits/tier")
def credits_tier(req: TierRequest, request: Request,
                 session=Depends(get_session)) -> Dict[str, Any]:
    """Tier setzen: free | paid | test (Zugangskontrolle)."""
    if req.tier not in ("free", "paid", "test"):
        raise HTTPException(status_code=422, detail="tier muss free|paid|test sein")
    from ..models import User

    user = session.get(User, req.user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="user not found")
    user.tier = req.tier
    session.add(user)
    session.commit()
    return {"ok": True, "user_id": req.user_id, "tier": user.tier}


@router.get("/credits/ledger")
def credits_ledger(request: Request, user_id: Optional[int] = None,
                   limit: int = 100,
                   session=Depends(get_session)) -> List[Dict[str, Any]]:
    """Journal (append-only) — neueste zuerst, optional je User."""
    from ..ledger import ledger_all
    from ..timeutil import iso_utc

    rows = ledger_all(session, limit=min(max(limit, 1), 500), user_id=user_id)
    return [{
        "id": r.id,
        "user_id": r.user_id,
        "delta_cents": r.delta_cents,
        "reason": r.reason,
        "ref_id": r.ref_id,
        "created_at": iso_utc(r.created_at) if r.created_at else None,
        "created_by": r.created_by,
    } for r in rows]


@router.get("/costing/summary")
def costing_summary(request: Request,
                    session=Depends(get_session)) -> Dict[str, Any]:
    """Einnahmen (TopUps) vs. Instanzkosten (Job-Kosten) + Budget-Rest."""
    from sqlmodel import func, select

    from ..models import CreditLedger, Recording

    topups = session.exec(
        select(func.coalesce(func.sum(CreditLedger.delta_cents), 0)).where(
            CreditLedger.delta_cents > 0)
    ).one()
    costs = session.exec(
        select(func.coalesce(func.sum(CreditLedger.delta_cents), 0)).where(
            CreditLedger.delta_cents < 0)
    ).one()
    jobs = session.exec(
        select(func.count()).select_from(Recording).where(
            Recording.cost_cents.is_not(None))
    ).one()
    return {
        "topup_cents": int(topups or 0),
        "cost_cents": int(-(costs or 0)),
        "net_cents": int((topups or 0) + (costs or 0)),
        "priced_jobs": int(jobs or 0),
    }


# ---------------------------------------------------------------------------
# Change 085: ETA-Learner (selbstlernende Faktoren)
# ---------------------------------------------------------------------------

class LearnerResetRequest(BaseModel):
    """POST /api/admin/learner/reset — Key optional; None = alle zurücksetzen."""
    phase_key: Optional[str] = None


def _learner_fallback(key: str) -> Optional[float]:
    """Statischer Fallback je Phase-Key (gleiche Quelle wie app/eta.py)."""
    from ..eta import (
        ALIGN_MS_PER_GROUP_FALLBACK, ASR_RTF, DIAR_RTF, ENHANCE_OVERHEAD,
        NOISE_REDUCE_OVERHEAD, PUNCT_OVERHEAD, VAD_OVERHEAD,
    )
    if key.startswith("asr:"):
        return ASR_RTF.get(key[4:])
    if key.startswith("diar:"):
        return DIAR_RTF.get(key[5:], 0.4)
    if key.startswith("enhance:"):
        return ENHANCE_OVERHEAD
    return {
        "vad": VAD_OVERHEAD,
        "noise_reduce": NOISE_REDUCE_OVERHEAD,
        "punc_truecase": PUNCT_OVERHEAD,
        "align": ALIGN_MS_PER_GROUP_FALLBACK,
    }.get(key)


@router.get("/learner/estimates")
def learner_estimates(request: Request) -> List[Dict[str, Any]]:
    """Gelernte ETA-Faktoren je Phase-Key (Historie n + Schätzung)."""
    from ..learner_store import load_learner

    learner = load_learner()
    out: List[Dict[str, Any]] = []
    for key in learner.keys():
        est = learner.estimate(key, fallback=_learner_fallback(key))
        out.append({
            "phase_key": key,
            "n": learner.sample_count(key),
            "factor": est.factor if est else None,
            "low": est.low if est else None,
            "high": est.high if est else None,
            "fallback": _learner_fallback(key),
        })
    out.sort(key=lambda x: x["phase_key"])
    return out


@router.post("/learner/reset")
def learner_reset(req: LearnerResetRequest, request: Request) -> Dict[str, Any]:
    """Lern-Historie zurücksetzen (ein Key oder alle) — nach Backend-/Image-Wechsel."""
    from ..learner_store import reset_estimates

    deleted = reset_estimates(req.phase_key or None)
    # TTL-Cache sofort invalidieren (sonst bis zu 5 s alte Schätzwerte).
    from .recordings import _learner_cache

    _learner_cache["ts"] = 0.0
    return {"deleted": deleted, "phase_key": req.phase_key}
