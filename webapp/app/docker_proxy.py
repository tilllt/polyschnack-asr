"""Docker control via the restrictive docker-socket-proxy (Task 4).

The webapp never sees the Docker socket. It talks HTTP to a
``tecriser/docker-socket-proxy`` container which only exposes the endpoints
we whitelist (CONTAINERS + INFO). This client wraps those endpoints:
list/state/start/stop/restart/logs + host info for the resource check.

A 404 from the Docker API means "container not created yet" (the GUI shows
the --no-start setup hint). A 503 means the proxy itself is unreachable.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import httpx

from .config import settings


class DockerProxyError(RuntimeError):
    """Raised for non-2xx responses or proxy failures."""


#: Muster im Docker-Fehlertext, die auf fehlende NVIDIA-GPU hinweisen
#: (Container mit runtime: nvidia auf einem Host ohne GPU/Toolkit).
_GPU_ERROR_PATTERNS = (
    "could not select device driver",
    "unknown runtime",
    "no such device",
    "nvidia",
)


def classify_docker_error(exc: Exception) -> Optional[str]:
    """Erkennt GPU-bedingte Start-Fehler und liefert eine deutsche Meldung.

    Gibt eine verständliche ``detail``-Meldung zurück, wenn der Fehler auf
    fehlende NVIDIA-GPU-Hardware bzw. fehlendes NVIDIA Container Toolkit
    hindeutet (Backend-Container mit ``runtime: nvidia``). Sonst ``None`` —
    der Aufrufer behandelt den Fehler dann als generischen Proxy-Fehler.
    """
    text = str(exc).lower()
    if any(p in text for p in _GPU_ERROR_PATTERNS):
        return (
            "Dieses Backend benötigt eine NVIDIA-GPU, die auf diesem Host "
            "nicht verfügbar ist (Container mit runtime: nvidia). Entweder "
            "NVIDIA Container Toolkit installieren oder ein CPU-fähiges "
            "Backend wählen."
        )
    return None


class DockerProxyClient:
    def __init__(
        self,
        base_url: Optional[str] = None,
        token: Optional[str] = None,
        timeout: float = 30.0,
        transport: Optional[httpx.BaseTransport] = None,
    ):
        self.base_url = (base_url or settings.DOCKER_PROXY_URL).rstrip("/")
        self.token = token if token is not None else settings.DOCKER_PROXY_TOKEN or None
        self.timeout = timeout
        self._transport = transport

    # ------------------------------------------------------------ helpers

    def _headers(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"} if self.token else {}

    def _request(self, method: str, path: str, expect: int = 200) -> httpx.Response:
        try:
            with httpx.Client(
                base_url=self.base_url,
                headers=self._headers(),
                timeout=self.timeout,
                transport=self._transport,
            ) as client:
                resp = client.request(method, path)
        except httpx.HTTPError as exc:
            raise DockerProxyError(f"docker-proxy unreachable ({exc})") from exc
        if resp.status_code == 404:
            raise DockerProxyError("container not created — run the --no-start setup first")
        if resp.status_code >= 400:
            raise DockerProxyError(
                f"docker-proxy {method} {path} -> HTTP {resp.status_code}: {resp.text[:200]}"
            )
        return resp

    # ------------------------------------------------------------ queries

    def list_containers(self, label: Optional[str] = None) -> List[Dict[str, Any]]:
        """List containers (all states). ``label`` filters docker labels."""
        path = "/containers/json?all=1"
        if label:
            path += f"&filters={{\"label\":[\"{label}\"]}}"
        resp = self._request("GET", path)
        return resp.json()

    def container_state(self, name: str) -> Optional[Dict[str, Any]]:
        """Return {status, health, running} or None when the container does not exist."""
        try:
            resp = self._request("GET", f"/containers/{name}/json")
        except DockerProxyError as exc:
            if "not created" in str(exc):
                return None
            raise
        data = resp.json()
        state = data.get("State", {})
        return {
            "status": state.get("Status"),
            "health": (state.get("Health") or {}).get("Status"),
            "running": state.get("Running", False),
        }

    def host_info(self) -> Dict[str, Any]:
        """Host-level info used by the resource check + GPU/CPU-Auto-Wahl.

        ``has_nvidia`` ist True, wenn das Docker-``/info`` eine nvidia-Runtime
        listet (NVIDIA Container Toolkit installiert) — Grundlage für die
        automatische GPU/CPU-Container-Wahl in der Admin-API.
        """
        resp = self._request("GET", "/info")
        data = resp.json()
        runtimes = data.get("Runtimes") or {}
        return {
            "mem_total_gb": round((data.get("MemTotal") or 0) / (1024 ** 3), 1),
            "ncpu": data.get("NCPU"),
            "docker_root_dir": data.get("DockerRootDir"),
            "has_nvidia": "nvidia" in runtimes,
        }

    # ------------------------------------------------------------ actions

    def start(self, name: str) -> None:
        self._request("POST", f"/containers/{name}/start")

    def stop(self, name: str) -> None:
        self._request("POST", f"/containers/{name}/stop")

    def restart(self, name: str) -> None:
        self._request("POST", f"/containers/{name}/restart")

    def logs(self, name: str, tail: int = 200) -> str:
        resp = self._request("GET", f"/containers/{name}/logs?stdout=1&stderr=1&tail={tail}")
        return resp.text


# Singleton per settings (cheap to recreate; kept for API symmetry with asr_client)
_client: Optional[DockerProxyClient] = None


def get_docker_client() -> DockerProxyClient:
    global _client
    if _client is None:
        _client = DockerProxyClient()
    return _client
