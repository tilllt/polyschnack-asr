"""Transcribe-Backend-Gate: Anon → nur laufende, Admin → Auto-Start."""
from __future__ import annotations

import types

import httpx
import pytest

from app.docker_proxy import DockerProxyClient
from app.routers.recordings import ensure_backend_available


class _FakeDocker:
    def __init__(self, state_by_name: dict, start_fails: bool = False):
        self.state_by_name = state_by_name
        self.start_fails = start_fails
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
        if self.start_fails:
            raise RuntimeError("docker start failed")
        self.started.append(name)
        self.state_by_name[name] = "running"


def _req(is_admin: bool):
    return types.SimpleNamespace(session={"is_admin": is_admin})


@pytest.fixture(autouse=True)
def _settings(monkeypatch):
    from app import config

    monkeypatch.setattr(config.settings, "OIDC_ENABLED", True)
    monkeypatch.setattr(config.settings, "POLYSCHNACK_DEFAULT_BACKEND", "pk-python")


@pytest.fixture(autouse=True)
def _docker_factory(monkeypatch):
    """Ersetzt get_docker_client in docker_proxy (recordings importiert es dort)."""
    holder = {"docker": None}

    def fake_get():
        return holder["docker"]

    monkeypatch.setattr("app.docker_proxy.get_docker_client", fake_get)
    return holder


def test_default_backend_noop(_docker_factory):
    docker = _FakeDocker({"polyschnack-asr": "running"})
    _docker_factory["docker"] = docker
    ensure_backend_available("", _req(False))  # leer = Default
    ensure_backend_available("pk-python", _req(False))
    assert docker.started == []


def test_running_backend_noop_for_anon(_docker_factory):
    docker = _FakeDocker({"polyschnack-qwen3": "running"})
    _docker_factory["docker"] = docker
    ensure_backend_available("qwen3-asr", _req(False))
    assert docker.started == []


def test_stopped_backend_rejected_for_anon(_docker_factory):
    docker = _FakeDocker({"polyschnack-qwen3": "stopped"})
    _docker_factory["docker"] = docker
    with pytest.raises(Exception) as ei:
        ensure_backend_available("qwen3-asr", _req(False))
    assert ei.value.status_code == 409
    assert "nicht gestartet" in ei.value.detail


def test_not_created_backend_rejected_for_anon(_docker_factory):
    docker = _FakeDocker({})  # qwen3 nie angelegt
    _docker_factory["docker"] = docker
    with pytest.raises(Exception) as ei:
        ensure_backend_available("qwen3-asr", _req(False))
    assert ei.value.status_code == 409


def test_admin_autostarts_stopped_backend(_docker_factory, monkeypatch):
    docker = _FakeDocker({"polyschnack-qwen3": "stopped"})
    _docker_factory["docker"] = docker
    monkeypatch.setattr(
        "app.resources.check_resources",
        lambda svc, docker: types.SimpleNamespace(ok=True, message=""),
    )
    ensure_backend_available("qwen3-asr", _req(True))
    assert docker.started == ["polyschnack-qwen3"]


def test_admin_autostart_health_wait_ok(_docker_factory, monkeypatch):
    # Container wird durch start() sofort "running" → Health-Wait endet beim 1. Poll
    docker = _FakeDocker({"polyschnack-cpp": "stopped"})
    _docker_factory["docker"] = docker
    monkeypatch.setattr(
        "app.resources.check_resources",
        lambda svc, docker: types.SimpleNamespace(ok=True, message=""),
    )
    ensure_backend_available("pk-cpp", _req(True))
    assert docker.started == ["polyschnack-cpp"]


def test_unknown_backend_404(_docker_factory):
    docker = _FakeDocker({})
    _docker_factory["docker"] = docker
    with pytest.raises(Exception) as ei:
        ensure_backend_available("nope-backend", _req(True))
    assert ei.value.status_code == 404
