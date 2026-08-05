"""Diarization-Fehlererkennung (Option B): CrispASR-diar-Service-Fehler.

Fehlerklassen bleiben erhalten — DiarizationError mit maschinenlesbarem
``code``. Neu seit Option B: service-unreachable (Verbindung), diar-error
(Proxy-Fehler mit detail.code), service-error (HTTP ohne detail).
Kein stilles [] bei Service-Problemen.
"""
import httpx
import pytest

from app.diarize import DiarizationError, diarize
from app.config import settings


class _FakeClient:
    def __init__(self, status, payload=None, detail=None):
        self._status = status
        self._payload = payload if payload is not None else (
            {"detail": detail} if detail else {})
        self.last_kwargs = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def post(self, url, files=None, data=None):
        self.last_kwargs = {"url": url, "files": files, "data": data}
        return httpx.Response(self._status, json=self._payload)


def _patch(monkeypatch, status, payload=None, detail=None):
    fc = _FakeClient(status, payload=payload, detail=detail)
    monkeypatch.setattr("app.diarize.httpx.Client", lambda *a, **k: fc)
    monkeypatch.setattr(settings, "DIAR_URL", "http://crispr-diar:5098")
    return fc


# ---------------------------------------------------------------------------
# DiarizationError Datentyp
# ---------------------------------------------------------------------------


def test_diarization_error_carries_code_and_message():
    e = DiarizationError("service-unreachable", "Diar-Service nicht erreichbar.")
    assert e.code == "service-unreachable"
    assert "erreichbar" in e.message
    assert "service-unreachable" in str(e)


# ---------------------------------------------------------------------------
# diarize() propagiert Fehler (kein stilles [] mehr)
# ---------------------------------------------------------------------------


def test_diarize_service_unreachable(monkeypatch, tmp_path):
    class _Boom:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def post(self, url, files=None, data=None):
            raise httpx.ConnectError("connection refused")

    monkeypatch.setattr("app.diarize.httpx.Client", lambda *a, **k: _Boom())
    monkeypatch.setattr(settings, "DIAR_URL", "http://crispr-diar:5098")
    p = tmp_path / "x.wav"
    p.write_bytes(b"RIFF....")
    with pytest.raises(DiarizationError) as ei:
        diarize(str(p))
    assert ei.value.code == "service-unreachable"


def test_diarize_proxy_detail_code_passthrough(monkeypatch, tmp_path):
    """Proxy-Fehler (z. B. load-failed) werden mit detail.code durchgereicht."""
    _patch(monkeypatch, 502, detail={"code": "load-failed",
                                     "message": "model load failed"})
    p = tmp_path / "x.wav"
    p.write_bytes(b"RIFF....")
    with pytest.raises(DiarizationError) as ei:
        diarize(str(p))
    assert ei.value.code == "load-failed"
    assert "model load failed" in ei.value.message


def test_diarize_http_error_without_detail(monkeypatch, tmp_path):
    """HTTP-Fehler ohne detail → service-error mit Statuscode."""
    _patch(monkeypatch, 500)
    p = tmp_path / "x.wav"
    p.write_bytes(b"RIFF....")
    with pytest.raises(DiarizationError) as ei:
        diarize(str(p))
    assert ei.value.code == "service-error"
    assert "500" in ei.value.message


# ---------------------------------------------------------------------------
# _normalise_speaker: A/B/C → SPEAKER_00/01
# ---------------------------------------------------------------------------


def test_normalise_speaker_labels():
    from app.diarize import _normalise_speaker

    assert _normalise_speaker("A") == "SPEAKER_00"
    assert _normalise_speaker("Z") == "SPEAKER_25"
    assert _normalise_speaker("SPEAKER_07") == "SPEAKER_07"
    assert _normalise_speaker("") == "SPEAKER_00"
    assert _normalise_speaker("?") == "SPEAKER_00"
