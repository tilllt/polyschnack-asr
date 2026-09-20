"""Feature matrix for the ASR backends — README + GUI (Task 3).

Flattens the service registry into the public matrix shape. The registry is
the single source of truth; values marked ``"verify"`` (e.g. ark/voxtral
``word_timestamps``) are checked against real API responses before being
flipped to booleans.

``reachable`` is the live container state (via docker-socket-proxy):
- True  — container is running
- False — container exists but is stopped, or was never created
- None  — docker-proxy unreachable / status unknown (frontend falls back
  to showing only the default backend for anonymous users)
The default backend (ps-pk-onnx, compose profile ``default``) is part of the
core stack and therefore always reported reachable.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter

from ..docker_proxy import DockerProxyClient, DockerProxyError, get_docker_client
from ..service_registry import SERVICES

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/models")


def _container_name(svc: Dict[str, Any]) -> str:
    """Container-Name = Service-Name aus der Registry (Option C)."""
    from ..service_registry import container_name
    return container_name(svc)


def _reachable(svc: Dict[str, Any], docker: Optional[DockerProxyClient]) -> Optional[bool]:
    """Live container state for one service; None when the proxy is down."""
    if svc["compose_profile"] == "default":
        return True  # core stack — the webapp itself depends on it
    if docker is None:
        return None
    try:
        state = docker.container_state(_container_name(svc))
    except DockerProxyError as exc:
        log.warning(
            "matrix: docker-proxy unreachable for service %s (%s): %s",
            svc["name"], _container_name(svc), exc,
        )
        return None
    if state is None:
        log.info(
            "matrix: service %s not created (run --no-start setup) — not offered",
            svc["name"],
        )
        return False
    return bool(state.get("running"))


def build_matrix(docker: Optional[DockerProxyClient] = None) -> List[Dict[str, Any]]:
    """Return one entry per registry service in the public matrix shape.

    ``docker`` may be injected for tests; defaults to the configured client.
    """
    if docker is None:
        try:
            docker = get_docker_client()
        except Exception as exc:  # settings missing in tests etc.
            log.debug("matrix: no docker client (%s) — reachable=None", exc)
            docker = None
    out: List[Dict[str, Any]] = []
    for s in SERVICES:
        caps = s["capabilities"]
        out.append({
            "name": s["name"],
            "backend": s["backend"],
            "model": s["model"],
            "type": s["type"],
            "status": s["status"],
            "reachable": _reachable(s, docker),
            "concurrency": s["concurrency"],
            "device": caps["device"],
            "languages": caps["languages"],
            "word_timestamps": caps["word_timestamps"],
            "streaming": caps["streaming"],
            "async_jobs": caps["async_jobs"],
            "noise_reduce": caps["noise_reduce"],
            "vad": caps["vad"],
            "diarization": caps["diarization"],
            "enhance": caps["enhance"],
            "requires": s["requires"],
        })
    return out


@router.get("/matrix")
def models_matrix() -> List[Dict[str, Any]]:
    return build_matrix()


# ---------------------------------------------------------------------------
# Backend-Fähigkeiten für die UI (Change 212)
# ---------------------------------------------------------------------------
#
# Das Optionen-Panel leitet die Verfügbarkeit seiner Optionen aus einer
# deklarativen Matrix ab. Alles, was dabei vom Backend abhängt (Live-Erkennung,
# native Satzzeichen/Großschreibung), kommt ausschließlich von hier — die
# Fähigkeiten werden aus den Adaptern gelesen (`get_client(name).capabilities`),
# nicht im Frontend hartkodiert. Je Fähigkeit gibt es damit genau eine Wahrheit.

backends_router = APIRouter(prefix="/api", tags=["backends"])


def build_backend_capabilities() -> Dict[str, Any]:
    """Fähigkeiten je aktivem Backend + für den Server-Default.

    Schlüssel ``""`` steht für „Server-Default“ (Aufnahme ohne explizite
    Backend-Wahl). Backends, deren Fähigkeiten nicht lesbar sind (Adapter-
    Fehler), fehlen in den Maps — das Frontend bietet die betroffene Option
    dann nicht an, statt einen Wert zu erfinden.
    """
    from ..asr_client import get_client
    from ..config import settings
    from ..service_registry import available_services

    default = settings.POLYSCHNACK_DEFAULT_BACKEND
    names = [s["name"] for s in available_services()]

    streaming: Dict[str, bool] = {}
    native_punctuation: Dict[str, bool] = {}
    # "" (Default) zuerst, dann alle aktiven Backends (Default nicht doppelt).
    for key in ["", *[n for n in names if n != default]]:
        backend = default if key == "" else key
        try:
            caps = get_client(backend).capabilities
        except Exception as exc:  # unbekanntes Backend / Adapter-Fehler
            log.warning("backends: capabilities for %r unavailable (%s)", backend, exc)
            continue
        streaming[key] = bool(caps.streaming)
        native_punctuation[key] = bool(caps.native_punctuation)

    return {
        "backends": names,
        "default": default,
        "streaming_supported": streaming.get("", False),
        "streaming_by_backend": streaming,
        "native_punctuation": native_punctuation,
    }


@backends_router.get("/backends")
def backends_capabilities() -> Dict[str, Any]:
    return build_backend_capabilities()
