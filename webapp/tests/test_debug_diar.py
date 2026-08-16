"""Tests für die TEMPORÄREN Debug-Endpunkte (/api/debug, Diarize-Diagnose 2026-08-16).

Abgedeckt:
- Gate: ohne POLYSCHNACK_DEBUG_TOKEN → 404 (deaktiviert), falsches Token → 403,
  korrektes Token (Query-Param oder X-Debug-Token-Header) → passiert.
- /diar/raw: gibt die unveränderte diarize_raw()-Antwort zurück; 404 bei
  unbekannter Recording-UID oder fehlender Audiodatei.
- /diar/logs: findet den diar-Container via docker-proxy und liefert die Logs;
  503 wenn der Proxy nicht erreichbar ist.
"""
import pytest
from fastapi.testclient import TestClient
from pathlib import Path

from app.config import settings
from app.docker_proxy import DockerProxyError
from app.main import app


class _FakeDocker:
    def __init__(self, containers=None):
        self.containers = containers or [
            {"Names": ["/polyschnack-diar-1"]},
            {"Names": ["/polyschnack-webapp-1"]},
        ]
        self.log_calls = []

    def list_containers(self, label=None):
        return self.containers

    def logs(self, name, tail=200):
        self.log_calls.append((name, tail))
        return "pyannote_seg_bench: chunked 4938749 frames -> 52 chunks"


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


def test_gate_disabled_ohne_token(client):
    assert settings.POLYSCHNACK_DEBUG_TOKEN == ""
    r = client.get("/api/debug/diar/raw?recording_id=x")
    assert r.status_code == 404


def test_gate_falsches_token(client, monkeypatch):
    monkeypatch.setattr(settings, "POLYSCHNACK_DEBUG_TOKEN", "geheim")
    r = client.get("/api/debug/diar/raw?recording_id=x&token=falsch")
    assert r.status_code == 403


def test_diar_raw_passthrough(client, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "POLYSCHNACK_DEBUG_TOKEN", "geheim")
    audio = tmp_path / "x.wav"
    audio.write_bytes(b"RIFF....")

    class _FakeRec:
        stored_path = str(audio)

    calls = {}

    def _fake_get_recording_by_uid(session, uid):
        calls["uid"] = uid
        return _FakeRec()

    def _fake_diarize_raw(path, num_speakers=None, method=None):
        calls["path"] = path
        calls["num_speakers"] = num_speakers
        calls["method"] = method
        return {"status_code": 200, "json": {"segments": [{"start": 0.0, "end": 1.0, "speaker": "A"}]}}

    monkeypatch.setattr("app.routers.debug.get_recording_by_uid", _fake_get_recording_by_uid)
    monkeypatch.setattr("app.routers.debug.diarize_raw", _fake_diarize_raw)

    r = client.get("/api/debug/diar/raw?recording_id=abc123&token=geheim&method=foxnose&num_speakers=2")
    assert r.status_code == 200
    body = r.json()
    assert body["status_code"] == 200
    assert body["json"]["segments"][0]["speaker"] == "A"
    assert calls["uid"] == "abc123"
    assert calls["method"] == "foxnose"
    assert calls["num_speakers"] == 2
    assert calls["path"] == str(audio)


def test_diar_raw_header_token(client, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "POLYSCHNACK_DEBUG_TOKEN", "geheim")
    audio = tmp_path / "x.wav"
    audio.write_bytes(b"RIFF....")

    class _FakeRec:
        stored_path = str(audio)

    monkeypatch.setattr(
        "app.routers.debug.get_recording_by_uid",
        lambda session, uid: _FakeRec(),
    )
    monkeypatch.setattr(
        "app.routers.debug.diarize_raw",
        lambda path, num_speakers=None, method=None: {"status_code": 200, "json": {}},
    )
    r = client.get("/api/debug/diar/raw?recording_id=abc123", headers={"X-Debug-Token": "geheim"})
    assert r.status_code == 200


def test_datei_fallback_aktiviert(client, monkeypatch, tmp_path):
    """Token aus <DATA_DIR>/debug_token — ohne Env, ohne Restart."""
    monkeypatch.setattr(settings, "POLYSCHNACK_DEBUG_TOKEN", "")
    token_file = Path(settings.DATA_DIR) / "debug_token"
    token_file.write_text("datei-token\n", encoding="utf-8")
    try:
        r = client.get("/api/debug/diar/raw?recording_id=x&token=datei-token")
        # Token ok → darf NICHT mehr 404/403 sein (Recording fehlt → 404 mit anderem Text)
        assert r.status_code == 404
        assert r.json().get("detail") == "recording not found"
        r2 = client.get("/api/debug/diar/raw?recording_id=x&token=falsch")
        assert r2.status_code == 403
    finally:
        token_file.unlink(missing_ok=True)


def test_diar_raw_unbekannte_uid(client, monkeypatch):
    monkeypatch.setattr(settings, "POLYSCHNACK_DEBUG_TOKEN", "geheim")
    monkeypatch.setattr("app.routers.debug.get_recording_by_uid", lambda session, uid: None)
    r = client.get("/api/debug/diar/raw?recording_id=unbekannt&token=geheim")
    assert r.status_code == 404


def test_diar_logs_passthrough(client, monkeypatch):
    monkeypatch.setattr(settings, "POLYSCHNACK_DEBUG_TOKEN", "geheim")
    fake = _FakeDocker()
    monkeypatch.setattr("app.routers.debug.get_docker_client", lambda: fake)
    r = client.get("/api/debug/diar/logs?token=geheim&lines=50")
    assert r.status_code == 200
    body = r.json()
    assert body["container"] == "/polyschnack-diar-1"
    assert "52 chunks" in body["logs"]
    assert fake.log_calls == [("/polyschnack-diar-1", 50)]


def test_diar_logs_proxy_down(client, monkeypatch):
    monkeypatch.setattr(settings, "POLYSCHNACK_DEBUG_TOKEN", "geheim")

    class _Down:
        def list_containers(self, label=None):
            raise DockerProxyError("docker-proxy unreachable (boom)")

    monkeypatch.setattr("app.routers.debug.get_docker_client", lambda: _Down())
    r = client.get("/api/debug/diar/logs?token=geheim")
    assert r.status_code == 503
