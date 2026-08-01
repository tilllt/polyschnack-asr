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
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from .. import app_config
from ..config import settings
from ..deps import require_admin
from ..docker_proxy import DockerProxyClient, DockerProxyError, get_docker_client
from ..queue import QueueError, queue_manager
from ..resources import check_resources
from ..service_registry import get_service, list_services, total_concurrency

router = APIRouter(prefix="/api/admin", dependencies=[Depends(require_admin)])

_HEALTH_WAIT_S = 120
_HEALTH_POLL_S = 2


def _container_name(svc: Dict[str, Any]) -> str:
    """compose container_name mapping: polyschnack-<profile>, default -> -asr."""
    profile = svc["compose_profile"]
    return f"polyschnack-{'asr' if profile == 'default' else profile}"


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
                           "docker compose --profile cpp --profile qwen3 --profile ark "
                           "--profile voxtral up -d --no-start",
            },
        )
    if state.get("running"):
        raise HTTPException(status_code=409, detail={"reason": "already_running"})

    docker.start(container)

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
