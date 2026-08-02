"""Matrix-Route: live reachable-Status pro Backend (Anon-Filter-Grundlage)."""
from __future__ import annotations

import httpx
import pytest

from app.docker_proxy import DockerProxyClient
from app.routers.matrix import build_matrix


def _docker(running: dict[str, bool]) -> DockerProxyClient:
    """Fake Docker-Proxy: per Container-Name → running? (fehlend = not created)."""

    def handler(request: httpx.Request) -> httpx.Response:
        # Pfad: /containers/<name>/json → zweitletztes Segment ist der Name
        parts = request.url.path.strip("/").split("/")
        name = parts[-2] if len(parts) >= 2 else parts[-1]
        if name in running:
            return httpx.Response(200, json={
                "State": {"Status": "running" if running[name] else "stopped",
                          "Running": running[name]},
            })
        return httpx.Response(404, json={"message": "No such container"})

    return DockerProxyClient(base_url="http://proxy:2375", transport=httpx.MockTransport(handler))


def test_matrix_reachable_true_when_running():
    docker = _docker({"polyschnack-cpp": True, "polyschnack-qwen3": True, "polyschnack-ark": True})
    m = {x["name"]: x for x in build_matrix(docker)}
    assert m["pk-cpp"]["reachable"] is True
    assert m["qwen3-asr"]["reachable"] is True
    assert m["ark-asr"]["reachable"] is True


def test_matrix_reachable_false_when_stopped_or_not_created():
    docker = _docker({"polyschnack-cpp": False})  # qwen3/ark fehlen → 404
    m = {x["name"]: x for x in build_matrix(docker)}
    assert m["pk-cpp"]["reachable"] is False
    assert m["qwen3-asr"]["reachable"] is False
    assert m["ark-asr"]["reachable"] is False


def test_matrix_default_always_reachable():
    # Nur der Kern-Stack läuft; optionale Container existieren nicht.
    docker = _docker({})
    m = {x["name"]: x for x in build_matrix(docker)}
    assert m["pk-python"]["reachable"] is True  # compose_profile default
    assert m["qwen3-asr"]["reachable"] is False


def test_matrix_reachable_null_when_proxy_down():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="proxy down")

    docker = DockerProxyClient(base_url="http://proxy:2375", transport=httpx.MockTransport(handler))
    m = {x["name"]: x for x in build_matrix(docker)}
    assert m["pk-python"]["reachable"] is True
    assert m["qwen3-asr"]["reachable"] is None


def test_matrix_has_reachable_field():
    for entry in build_matrix(_docker({})):
        assert "reachable" in entry
