"""Admin-API-Tests (Task 8) — Fake-Docker, gemockte Queue, direkte Handler-Aufrufe."""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from app import queue as queue_mod
from app.queue import QueueManager
from app.routers import admin


class _FakeDocker:
    def __init__(self, mem_total_gb=64.0, state=None, health=None):
        self.mem = mem_total_gb
        self._state = state          # "running" | "stopped" | None (not created)
        self._health = health
        self.started: list = []
        self.stopped: list = []

    def host_info(self):
        return {"mem_total_gb": self.mem, "ncpu": 16, "docker_root_dir": "/var/lib/docker"}

    def list_containers(self):
        return []

    def container_state(self, name):
        if self._state is None:
            return None
        return {"status": self._state, "health": self._health, "running": self._state == "running"}

    def start(self, name):
        self.started.append(name)
        self._state = "running"
        self._health = "healthy"

    def stop(self, name):
        self.stopped.append(name)
        self._state = "stopped"

    def restart(self, name):
        self.stopped.append(name)
        self.started.append(name)

    def logs(self, name, tail=200):
        return "fake log line\n"


@pytest.fixture()
def docker(monkeypatch):
    d = _FakeDocker(state="stopped")
    monkeypatch.setattr(admin, "get_docker_client", lambda: d)
    return d


@pytest.fixture()
def qm(monkeypatch):
    class _FakeCrud:
        def set_queued(self, session, rec_id, backend): pass
        def set_processing(self, session, rec_id): pass
        def get_recording(self, session, rec_id): return None
        def avg_recent_processing_ms(self, session, limit=20): return 0.0

    fake = _FakeCrud()
    monkeypatch.setattr(queue_mod.crud, "set_queued", fake.set_queued)
    monkeypatch.setattr(queue_mod.crud, "set_processing", fake.set_processing)
    monkeypatch.setattr(queue_mod.crud, "get_recording", fake.get_recording)
    monkeypatch.setattr(queue_mod.crud, "avg_recent_processing_ms", fake.avg_recent_processing_ms)
    m = QueueManager(max_queue_len=5)
    monkeypatch.setattr(admin, "queue_manager", m)
    yield m
    m.stop()


# ------------------------------------------------------------- start


def test_start_ok_when_healthy(docker, tmp_path, monkeypatch):
    monkeypatch.setattr(admin.settings, "DATA_DIR", tmp_path)
    r = admin.start_service("pk-cpp", None)
    assert r["status"] == "running" and r["health"] == "healthy"
    assert docker.started == ["polyschnack-cpp"]


def test_start_unknown_service_404(docker, tmp_path, monkeypatch):
    monkeypatch.setattr(admin.settings, "DATA_DIR", tmp_path)
    with pytest.raises(HTTPException) as ei:
        admin.start_service("nope", None)
    assert ei.value.status_code == 404


def test_start_insufficient_resources_409(docker, tmp_path, monkeypatch):
    monkeypatch.setattr(admin.settings, "DATA_DIR", tmp_path)
    docker.mem = 2.0  # zu wenig RAM für pk-cpp (braucht 4 GB)
    with pytest.raises(HTTPException) as ei:
        admin.start_service("pk-cpp", None)
    assert ei.value.status_code == 409
    assert ei.value.detail["reason"] == "insufficient_resources"
    assert "ram_gb" in ei.value.detail["missing"]
    assert docker.started == []  # kein Startversuch


def test_start_not_created_409(docker, tmp_path, monkeypatch):
    monkeypatch.setattr(admin.settings, "DATA_DIR", tmp_path)
    docker._state = None
    with pytest.raises(HTTPException) as ei:
        admin.start_service("pk-cpp", None)
    assert ei.value.status_code == 409
    assert ei.value.detail["reason"] == "not_created"


def test_start_already_running_409(docker, tmp_path, monkeypatch):
    monkeypatch.setattr(admin.settings, "DATA_DIR", tmp_path)
    docker._state = "running"
    with pytest.raises(HTTPException) as ei:
        admin.start_service("pk-cpp", None)
    assert ei.value.status_code == 409
    assert ei.value.detail["reason"] == "already_running"


# ------------------------------------------------------------- stop


def test_stop_blocked_by_active_jobs(docker, qm, tmp_path, monkeypatch):
    monkeypatch.setattr(admin.settings, "DATA_DIR", tmp_path)
    qm.enqueue(1, None, "pk-cpp")
    with pytest.raises(HTTPException) as ei:
        admin.stop_service("pk-cpp", None)
    assert ei.value.status_code == 409
    assert ei.value.detail["reason"] == "active_jobs"
    assert docker.stopped == []


def test_stop_ok_without_jobs(docker, qm, tmp_path, monkeypatch):
    monkeypatch.setattr(admin.settings, "DATA_DIR", tmp_path)
    docker._state = "running"  # Container läuft
    r = admin.stop_service("pk-cpp", None)
    assert r["status"] == "stopped"
    assert docker.stopped == ["polyschnack-cpp"]


# ------------------------------------------------------------- config


def test_put_config_unknown_backend_422(docker, tmp_path, monkeypatch):
    monkeypatch.setattr(admin.settings, "DATA_DIR", tmp_path)
    with pytest.raises(HTTPException) as ei:
        admin.put_config(type("P", (), {"default_backend": "nope"})(), None)
    assert ei.value.status_code == 422


def test_put_config_auto_starts_stopped_backend(docker, tmp_path, monkeypatch):
    """Entscheidung 8: Wechsel auf nicht-laufendes Backend startet es automatisch."""
    monkeypatch.setattr(admin.settings, "DATA_DIR", tmp_path)
    r = admin.put_config(type("P", (), {"default_backend": "qwen3-asr"})(), None)
    assert r["default_backend"] == "qwen3-asr"
    assert docker.started == ["polyschnack-qwen3"]


def test_put_config_insufficient_resources_keeps_default(docker, tmp_path, monkeypatch):
    monkeypatch.setattr(admin.settings, "DATA_DIR", tmp_path)
    docker.mem = 1.0
    with pytest.raises(HTTPException) as ei:
        admin.put_config(type("P", (), {"default_backend": "qwen3-asr"})(), None)
    assert ei.value.status_code == 409
    # Default bleibt unverändert (kein app_config.set erfolgt)
    from app import app_config
    assert app_config.get("default_backend") is None


def test_config_roundtrip(docker, tmp_path, monkeypatch):
    monkeypatch.setattr(admin.settings, "DATA_DIR", tmp_path)
    admin.put_config(type("P", (), {"default_backend": "pk-cpp"})(), None)
    cfg = admin.admin_config()
    assert cfg["default_backend"] == "pk-cpp"
    admin.reset_config()
    cfg2 = admin.admin_config()
    assert cfg2["default_backend"] == admin.settings.POLYSCHNACK_DEFAULT_BACKEND
