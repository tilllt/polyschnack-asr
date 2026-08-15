"""OpenAI-Proxy: Backend-Hopping via model-Parameter + Formate.

Auth wird über ein identitäts-Fake ersetzt (der echte Key-Flow ist in
test_apikeys/test_apikey_access abgedeckt); hier geht es um Routing und
Antwort-Formate.
"""
from __future__ import annotations

import io
from unittest import mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers.openai_proxy import router as proxy_router


class _FakeClient:
    def __init__(self, *args, **kwargs):
        pass

    def transcribe(self, audio_bytes, filename, mime):
        return {
            "text": "Hallo Welt",
            "language": "de",
            "duration": 1.23,
            "segments": [
                {"start": 0.0, "end": 0.6, "text": "Hallo"},
                {"start": 0.6, "end": 1.23, "text": "Welt"},
            ],
        }


@pytest.fixture()
def client():
    # Auth durchstechen: dependency_overrides ersetzt _require_api_key —
    # der echte API-Key-Flow ist in test_apikey_access abgedeckt.
    class _FakeId:
        pass

    from starlette.middleware.sessions import SessionMiddleware

    from app.routers.openai_proxy import _require_api_key

    app = FastAPI()
    app.add_middleware(SessionMiddleware, secret_key="test-secret")
    app.dependency_overrides[_require_api_key] = lambda: _FakeId()
    app.include_router(proxy_router)
    return TestClient(app)


def test_proxy_ohne_api_key_401():
    """Review P0.2: Der Proxy darf anon-Sessions NICHT akzeptieren —
    ohne gültigen Bearer-Key kommt 401 (kein offenes Compute)."""
    from app.main import app as _main_app
    from fastapi.testclient import TestClient

    tc = TestClient(_main_app)
    resp = tc.post(
        "/v1/audio/transcriptions",
        files={"file": ("a.wav", b"x", "audio/wav")},
    )
    assert resp.status_code == 401


def _patch_get_client(client):
    """get_client mocken — liefert _FakeClient und merkt sich den Backend-Namen."""
    calls = {}

    def fake_get_client(backend=None):
        calls["backend"] = backend
        return _FakeClient()

    patcher = mock.patch("app.routers.openai_proxy.get_client", side_effect=fake_get_client)
    patcher.start()
    return calls, patcher


def _upload(client, **data):
    files = {"file": ("test.ogg", io.BytesIO(b"RIFFfakeaudio"), "audio/ogg")}
    return client.post("/v1/audio/transcriptions", files=files, data=data)


def test_proxy_default_backend_json(client):
    calls, p = _patch_get_client(client)
    try:
        r = _upload(client)
    finally:
        p.stop()
    assert r.status_code == 200
    assert r.json()["text"] == "Hallo Welt"
    assert calls["backend"] == "ps-pk-onnx"  # Default (kein model)


def test_proxy_model_mapping_qwen3(client):
    calls, p = _patch_get_client(client)
    try:
        r = _upload(client, model="qwen3-asr-0.6b")
    finally:
        p.stop()
    assert r.status_code == 200
    assert calls["backend"] == "crispr-qwen3"


def test_proxy_explicit_backend_field(client):
    calls, p = _patch_get_client(client)
    try:
        r = _upload(client, backend="crispr-canary")
    finally:
        p.stop()
    assert r.status_code == 200
    assert calls["backend"] == "crispr-canary"


def test_proxy_model_alias_parakeet(client):
    calls, p = _patch_get_client(client)
    try:
        r = _upload(client, model="istupakov/parakeet-tdt-0.6b-v3-onnx")
    finally:
        p.stop()
    assert r.status_code == 200
    assert calls["backend"] == "ps-pk-onnx"


def test_proxy_unknown_model_400(client):
    r = _upload(client, model="does-not-exist")
    assert r.status_code == 400
    assert "unknown model" in r.json()["detail"]


def test_proxy_unknown_backend_400(client):
    r = _upload(client, backend="nope")
    assert r.status_code == 400


def test_proxy_response_formats(client):
    calls, p = _patch_get_client(client)
    try:
        r_text = _upload(client, response_format="text")
        assert r_text.status_code == 200
        assert r_text.text == "Hallo Welt"

        r_v = _upload(client, response_format="verbose_json")
        assert r_v.status_code == 200
        body = r_v.json()
        assert body["text"] == "Hallo Welt"
        assert len(body["segments"]) == 2
        assert body["duration"] == 1.23

        r_srt = _upload(client, response_format="srt")
        assert "--> " in r_srt.text

        r_vtt = _upload(client, response_format="vtt")
        assert r_vtt.text.startswith("WEBVTT")

        r_bad = _upload(client, response_format="xml")
        assert r_bad.status_code == 400
        assert "invalid response_format" in r_bad.json()["detail"]
    finally:
        p.stop()


def test_proxy_empty_file_400(client):
    files = {"file": ("empty.ogg", io.BytesIO(b""), "audio/ogg")}
    r = client.post("/v1/audio/transcriptions", files=files, data={})
    assert r.status_code == 400


def test_proxy_backend_error_502(client):
    def boom(*a, **k):
        raise RuntimeError("backend down")

    p = mock.patch("app.routers.openai_proxy.get_client", side_effect=boom)
    p.start()
    try:
        r = _upload(client)
    finally:
        p.stop()
    assert r.status_code == 502
    assert "backend" in r.json()["detail"]
