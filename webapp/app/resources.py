"""Resource availability check before container starts (Task 5).

Best-effort guard (documented in the plan): RAM/disk are measured exactly,
VRAM only for our own servers (pk-python reports it via /health); foreign
images yield ``unknown`` -> warning instead of block. The real protection
after a start is the health-wait + log excerpt.
"""
from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import httpx

from .config import settings
from .docker_proxy import DockerProxyClient

_RESOURCE_KEYS = ("vram_gb", "ram_gb", "disk_gb")


@dataclass
class ResourceReport:
    ok: bool
    service: str
    required: Dict[str, float]
    available: Dict[str, Any]  # float or "unknown"
    missing: Dict[str, float]
    unknown: List[str]
    message: str


def _running_ram_used_gb(docker: DockerProxyClient) -> float:
    """Sum of Memory limits of running containers (GB) — what is already committed."""
    total = 0.0
    try:
        for c in docker.list_containers():
            if c.get("State") in ("running", "restarting"):
                mem = (c.get("HostConfig") or {}).get("Memory") or 0
                if mem:
                    total += mem / (1024 ** 3)
    except Exception:
        pass  # proxy hiccup -> treat as 0, availability degrades to unknown
    return round(total, 1)


def _disk_free_gb() -> Optional[float]:
    try:
        usage = shutil.disk_usage(str(settings.DATA_DIR))
        return round(usage.free / (1024 ** 3), 1)
    except OSError:
        return None


def _vram_free_gb(service: Dict[str, Any], docker: DockerProxyClient) -> Optional[float]:
    """VRAM via the service's /health resources block — only our own servers.

    ``health_url`` unset -> None (unknown). ``""`` -> settings.ASR_URL.
    """
    if "health_url" not in service:
        return None
    url = service["health_url"] or f"{settings.ASR_URL}/health"
    try:
        resp = httpx.get(url, timeout=5)
        resp.raise_for_status()
        return resp.json().get("resources", {}).get("vram_free_gb")
    except Exception:
        return None


def check_resources(service: Dict[str, Any], docker: DockerProxyClient) -> ResourceReport:
    """Compare ``service["requires"]`` against measured availability."""
    required = service["requires"]
    avail: Dict[str, Any] = {}
    unknown: List[str] = []
    missing: Dict[str, float] = {}

    host = docker.host_info()  # raises DockerProxyError when the proxy is down
    ram_used = _running_ram_used_gb(docker)
    avail["ram_gb"] = round(max(host["mem_total_gb"] - ram_used, 0.0), 1)

    disk = _disk_free_gb()
    avail["disk_gb"] = disk if disk is not None else "unknown"
    if disk is None:
        unknown.append("disk_gb")

    vram = _vram_free_gb(service, docker)
    avail["vram_gb"] = vram if vram is not None else "unknown"
    if vram is None:
        unknown.append("vram_gb")

    for k in _RESOURCE_KEYS:
        a = avail.get(k)
        if isinstance(a, (int, float)) and a < required[k]:
            missing[k] = round(required[k] - a, 1)

    ok = not missing
    if missing:
        parts = ", ".join(f"{k}: need {required[k]} GB, have {avail[k]} GB" for k in missing)
        message = f"Not enough resources — {parts}"
    elif unknown:
        message = f"ok (unchecked: {', '.join(unknown)})"
    else:
        message = "ok"
    return ResourceReport(
        ok=ok, service=service["name"], required=required,
        available=avail, missing=missing, unknown=unknown, message=message,
    )
