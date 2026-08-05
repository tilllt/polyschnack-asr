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
    """container_name aus der Registry — einzige Quelle (kein hartkodiertes Mapping)."""
    return svc["container_name"]


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
