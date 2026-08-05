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
    assert calls == [("POST", "/containers/crispr-pk-cpp/start")]


def test_stop_and_restart():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, request.url.path))
        return httpx.Response(204)

    c = _client(handler)
    c.stop("crispr-qwen3")
    c.restart("crispr-ark")
    assert calls == [
        ("POST", "/containers/crispr-qwen3/stop"),
        ("POST", "/containers/crispr-ark/restart"),
    ]


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
