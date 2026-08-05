"""GPU-Fehler-Mapping: Backend-Start ohne NVIDIA-GPU → verständliche Meldung (Task A4)."""
from __future__ import annotations

import types

import httpx
import pytest

from app.docker_proxy import DockerProxyClient, DockerProxyError, classify_docker_error
from app.routers.recordings import ensure_backend_available


# ---------------------------------------------------------------------------
# classify_docker_error
# ---------------------------------------------------------------------------
def test_classify_select_device_driver():
    exc = DockerProxyError(
        "docker-proxy POST /containers/x/start -> HTTP 500: "
        "could not select device driver \"nvidia\" with capabilities: [[gpu]]"
    )
    msg = classify_docker_error(exc)
    assert msg is not None
    assert "NVIDIA-GPU" in msg


def test_classify_unknown_runtime():
    exc = DockerProxyError(
        "docker-proxy POST /containers/x/start -> HTTP 500: Unknown runtime spec nvidia"
    )
    assert classify_docker_error(exc) is not None


def test_classify_no_such_device():
    exc = DockerProxyError("docker-proxy POST /containers/x/start -> HTTP 500: no such device")
    assert classify_docker_error(exc) is not None


def test_classify_unrelated_error_returns_none():
    exc = DockerProxyError("docker-proxy POST /containers/x/start -> HTTP 500: boom")
    assert classify_docker_error(exc) is None


def test_classify_httpx_unreachable_returns_none():
    exc = DockerProxyError("docker-proxy unreachable (connection refused)")
    assert classify_docker_error(exc) is None


# ---------------------------------------------------------------------------
# Mapping in ensure_backend_available (Admin-Autostart)
# ---------------------------------------------------------------------------
class _GpuFailingDocker:
    """Fake-Docker: start() wirft DockerProxyError mit GPU-Muster."""

    def __init__(self, state_by_name: dict):
        self.state_by_name = state_by_name
        self.started: list[str] = []
        self._fake = DockerProxyClient(
            base_url="http://proxy:2375",
            transport=httpx.MockTransport(self._handler),
        )

    def _handler(self, request: httpx.Request) -> httpx.Response:
        parts = request.url.path.strip("/").split("/")
        name = parts[-2] if len(parts) >= 2 else parts[-1]
        if name not in self.state_by_name:
            return httpx.Response(404, json={"message": "No such container"})
        state = self.state_by_name[name]
        if state == "stopped":
            return httpx.Response(200, json={"State": {"Status": "stopped", "Running": False}})
        return httpx.Response(200, json={"State": {"Status": "running", "Running": True}})

    def container_state(self, name: str):
        return self._fake.container_state(name)

    def start(self, name: str):
        raise DockerProxyError(
            f"docker-proxy POST /containers/{name}/start -> HTTP 500: "
            'could not select device driver "nvidia" with capabilities: [[gpu]]'
        )


def _req(is_admin: bool):
    return types.SimpleNamespace(session={"is_admin": is_admin})


@pytest.fixture(autouse=True)
def _settings(monkeypatch):
    from app import config

    monkeypatch.setattr(config.settings, "OIDC_ENABLED", True)
    monkeypatch.setattr(config.settings, "POLYSCHNACK_DEFAULT_BACKEND", "ps-pk-onnx")


@pytest.fixture(autouse=True)
def _docker_factory(monkeypatch):
    holder = {"docker": None}

    def fake_get():
        return holder["docker"]

    monkeypatch.setattr("app.docker_proxy.get_docker_client", fake_get)
    return holder


def test_admin_autostart_gpu_error_maps_to_409(_docker_factory, monkeypatch):
    """GPU-Start-Fehler → 409 mit verständlicher Meldung statt generischem 503."""
    docker = _GpuFailingDocker({"crispr-qwen3": "stopped"})
    _docker_factory["docker"] = docker
    monkeypatch.setattr(
        "app.resources.check_resources",
        lambda svc, docker: types.SimpleNamespace(ok=True, message=""),
    )
    with pytest.raises(Exception) as ei:
        ensure_backend_available("crispr-qwen3", _req(True))
    assert ei.value.status_code == 409
    detail = ei.value.detail
    assert "NVIDIA-GPU" in detail.get("message", "")


def test_admin_autostart_unrelated_error_still_503(_docker_factory, monkeypatch):
    """Nicht-GPU-Fehler bleibt beim bisherigen 503-Verhalten."""
    class _FailingDocker(_GpuFailingDocker):
        def start(self, name: str):
            raise DockerProxyError("docker-proxy POST -> HTTP 500: boom")

    docker = _FailingDocker({"crispr-qwen3": "stopped"})
    _docker_factory["docker"] = docker
    monkeypatch.setattr(
        "app.resources.check_resources",
        lambda svc, docker: types.SimpleNamespace(ok=True, message=""),
    )
    with pytest.raises(Exception) as ei:
        ensure_backend_available("crispr-qwen3", _req(True))
    assert ei.value.status_code == 503
