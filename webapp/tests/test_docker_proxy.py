"""Docker-Proxy-Client-Tests (Task 4) — httpx MockTransport statt echtem Socket."""
from __future__ import annotations

import httpx
import pytest

from app.docker_proxy import DockerProxyClient, DockerProxyError


def _client(handler) -> DockerProxyClient:
    transport = httpx.MockTransport(handler)
    return DockerProxyClient(base_url="http://proxy:2375", transport=transport)


def test_start_posts_to_container_endpoint():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, request.url.path))
        return httpx.Response(204)

    c = _client(handler)
    c.start("crispr-pk-cpp")
    # Change 188: vor der Aktion wird der echte Container aufgelöst
    # (exakter Name → sonst Compose-Label); hier greift der exakte Name.
    assert calls == [
        ("GET", "/containers/crispr-pk-cpp/json"),
        ("POST", "/containers/crispr-pk-cpp/start"),
    ]


def test_stop_and_restart():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, request.url.path))
        return httpx.Response(204)

    c = _client(handler)
    c.stop("crispr-qwen3")
    c.restart("crispr-ark")
    assert calls == [
        ("GET", "/containers/crispr-qwen3/json"),
        ("POST", "/containers/crispr-qwen3/stop"),
        ("GET", "/containers/crispr-ark/json"),
        ("POST", "/containers/crispr-ark/restart"),
    ]


def test_resolve_container_faellt_auf_compose_label_zurueck():
    """Change 188: Compose-Container heißen <projekt>-<service>-<index>
    (polyschnack-crispr-canary-1). Der kurze Registry-Name liefert 404 —
    dann wird über das Label com.docker.compose.service gesucht, sonst
    meldet die Matrix „nicht erreichbar" und die GUI kann das Backend
    nicht starten (Live-Befund 2026-09-14: crispr-canary lief, aber
    reachable=false)."""
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, request.url.path, str(request.url)))
        if request.url.path == "/containers/crispr-canary/json":
            return httpx.Response(404, json={"message": "No such container"})
        if request.url.path == "/containers/json":
            return httpx.Response(200, json=[
                {"Id": "abc123", "Names": ["/polyschnack-crispr-canary-1"]},
            ])
        if request.url.path == "/containers/abc123/json":
            return httpx.Response(200, json={
                "State": {"Status": "running", "Running": True,
                          "Health": {"Status": "healthy"}},
            })
        if request.url.path == "/containers/abc123/start":
            return httpx.Response(204)
        return httpx.Response(500, json={"message": "unerwartet"})

    c = _client(handler)
    assert c.resolve_container("crispr-canary") == "abc123"
    state = c.container_state("crispr-canary")
    assert state == {"status": "running", "health": "healthy", "running": True}
    c.start("crispr-canary")
    assert ("POST", "/containers/abc123/start", "http://proxy:2375/containers/abc123/start") in calls
    assert any("com.docker.compose.service=crispr-canary" in url for _m, _p, url in calls)


def test_resolve_container_unbekannt_gibt_none():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/containers/json":
            return httpx.Response(200, json=[])
        return httpx.Response(404, json={"message": "No such container"})

    c = _client(handler)
    assert c.resolve_container("gibt-es-nicht") is None
    assert c.container_state("gibt-es-nicht") is None


def test_container_state_parses_health():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "State": {"Status": "running", "Running": True,
                      "Health": {"Status": "healthy"}},
        })

    c = _client(handler)
    st = c.container_state("ps-pk-onnx")
    assert st == {"status": "running", "health": "healthy", "running": True}


def test_container_state_none_when_not_created():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"message": "No such container"})

    c = _client(handler)
    assert c.container_state("crispr-pk-cpp") is None


def test_start_not_created_raises_helpful_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"message": "No such container"})

    c = _client(handler)
    with pytest.raises(DockerProxyError, match="--no-start"):
        c.start("crispr-pk-cpp")


def test_proxy_down_raises():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    c = _client(handler)
    with pytest.raises(DockerProxyError, match="unreachable"):
        c.list_containers()


def test_host_info_parses_memory():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"MemTotal": 32 * 1024 ** 3, "NCPU": 16,
                                         "DockerRootDir": "/var/lib/docker"})

    c = _client(handler)
    info = c.host_info()
    assert info["mem_total_gb"] == 32.0
    assert info["ncpu"] == 16
    assert info["docker_root_dir"] == "/var/lib/docker"


def test_host_info_has_nvidia_when_runtime_present():
    """NVIDIA Container Toolkit erkannt: Docker /info → Runtimes enthält nvidia."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"MemTotal": 32 * 1024 ** 3,
                                         "Runtimes": {"runc": {}, "nvidia": {}}})

    c = _client(handler)
    assert c.host_info()["has_nvidia"] is True


def test_host_info_no_nvidia_without_runtime():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"MemTotal": 16 * 1024 ** 3,
                                         "Runtimes": {"runc": {}}})

    c = _client(handler)
    assert c.host_info()["has_nvidia"] is False


def test_list_containers_passes_label_filter():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(200, json=[])

    c = _client(handler)
    c.list_containers(label="com.docker.compose.project=polyschnack")
    assert "filters=" in captured["url"] and "polyschnack" in captured["url"]
