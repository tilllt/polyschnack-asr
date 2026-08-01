"""Ressourcen-Check-Tests (Task 5) — Fake-Docker statt Proxy."""
from __future__ import annotations

from app import resources
from app.config import settings
from app.resources import check_resources


class _FakeDocker:
    def __init__(self, mem_total_gb=32.0, running_limits=()):
        self.mem = mem_total_gb
        self.running_limits = list(running_limits)

    def host_info(self):
        return {"mem_total_gb": self.mem, "ncpu": 8, "docker_root_dir": "/var/lib/docker"}

    def list_containers(self):
        return [{"State": "running", "HostConfig": {"Memory": int(lim * 1024 ** 3)}}
                for lim in self.running_limits]


_SERVICE = {
    "name": "pk-cpp",
    "requires": {"vram_gb": 2, "ram_gb": 4, "disk_gb": 2},
    # no health_url -> vram unknown
}


def test_ok_when_enough_resources(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "DATA_DIR", tmp_path)
    rep = check_resources(_SERVICE, _FakeDocker(mem_total_gb=32, running_limits=(8,)))
    assert rep.ok is True
    assert rep.missing == {}
    assert rep.available["ram_gb"] == 24.0  # 32 - 8 (asr limit)
    assert rep.unknown == ["vram_gb"]  # foreign image, no health_url


def test_missing_ram_blocks(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "DATA_DIR", tmp_path)
    rep = check_resources(_SERVICE, _FakeDocker(mem_total_gb=4, running_limits=(8,)))
    assert rep.ok is False
    assert "ram_gb" in rep.missing
    assert "Not enough resources" in rep.message


def test_disk_unknown_when_datadir_missing(monkeypatch):
    monkeypatch.setattr(settings, "DATA_DIR", "/nonexistent/xyz")
    rep = check_resources(_SERVICE, _FakeDocker(mem_total_gb=32))
    assert "disk_gb" in rep.unknown
    assert rep.ok is True  # warning, not block


def test_vram_from_own_health_endpoint(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "DATA_DIR", tmp_path)

    class _Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"resources": {"vram_free_gb": 18.5}}

    monkeypatch.setattr(resources.httpx, "get", lambda url, timeout=5: _Resp())
    svc = dict(_SERVICE, health_url="")  # "" -> settings.ASR_URL
    rep = check_resources(svc, _FakeDocker(mem_total_gb=32))
    assert rep.available["vram_gb"] == 18.5
    assert rep.ok is True
    assert "vram_gb" not in rep.unknown


def test_vram_unknown_when_health_fails(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "DATA_DIR", tmp_path)

    def _boom(url, timeout=5):
        raise OSError("service not running")

    monkeypatch.setattr(resources.httpx, "get", _boom)
    svc = dict(_SERVICE, health_url="")
    rep = check_resources(svc, _FakeDocker(mem_total_gb=32))
    assert rep.available["vram_gb"] == "unknown"
    assert "vram_gb" in rep.unknown
    assert rep.ok is True
