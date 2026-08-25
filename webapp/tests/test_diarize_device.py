"""diarize.py als HTTP-Client für den CrispASR-diar-Service (Option B, Task 4).

Die pyannote-Pipeline wurde durch den CrispASR-Server ersetzt: diarize()
ruft POST /v1/audio/transcriptions mit diarize=true + diarized_json auf
und normalisiert die Speaker-Labels A/B/C → SPEAKER_00/01/….
"""
from __future__ import annotations

import httpx
import pytest

import app.diarize as d
from app.config import settings


class _FakeClient:
    def __init__(self, status, payload):
        self._status, self._payload = status, payload
        self.last_kwargs = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def post(self, url, files=None, data=None):
        self.last_kwargs = {"url": url, "files": files, "data": data}
        return httpx.Response(self._status, json=self._payload)


def _patch(monkeypatch, status, payload):
    fc = _FakeClient(status, payload)
    monkeypatch.setattr(d.httpx, "Client", lambda *a, **k: fc)
    monkeypatch.setattr(settings, "DIAR_URL", "http://crispr-diar:5098")
    return fc


def test_diarize_maps_segments_and_normalises_speakers(monkeypatch, tmp_path):
    fc = _patch(monkeypatch, 200, {"segments": [
        {"start": 0.0, "end": 10.0, "speaker": "A"},
        {"start": 10.0, "end": 20.0, "speaker": "B"},
    ]})
    p = tmp_path / "a.wav"
    p.write_bytes(b"RIFF....")
    out = d.diarize(str(p))
    assert out[0]["speaker"] == "SPEAKER_00"
    assert out[1]["speaker"] == "SPEAKER_01"
    assert out[0]["start"] == 0.0 and out[0]["end"] == 10.0
    # Request enthält diarize=true + diarized_json + Methode
    data = fc.last_kwargs["data"]
    assert data["diarize"] == "true"
    assert data["response_format"] == "diarized_json"
    assert data["diarize_method"] == settings.DIARIZE_METHOD
    # URL zeigt auf den diar-Service
    assert fc.last_kwargs["url"] == "http://crispr-diar:5098/v1/audio/transcriptions"


def test_diarize_sends_max_speakers(monkeypatch, tmp_path):
    fc = _patch(monkeypatch, 200, {"segments": []})
    p = tmp_path / "a.wav"
    p.write_bytes(b"RIFF....")
    d.diarize(str(p), num_speakers=2)
    assert fc.last_kwargs["data"]["diarize_max_speakers"] == "2"


def test_diarize_service_unreachable(monkeypatch, tmp_path):
    class _Boom:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def post(self, url, files=None, data=None):
            raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(d.httpx, "Client", lambda *a, **k: _Boom())
    monkeypatch.setattr(settings, "DIAR_URL", "http://crispr-diar:5098")
    p = tmp_path / "a.wav"
    p.write_bytes(b"RIFF....")
    with pytest.raises(d.DiarizationError) as ei:
        d.diarize(str(p))
    assert ei.value.code == "service-unreachable"


def test_diarize_proxy_error_mapped(monkeypatch, tmp_path):
    _patch(monkeypatch, 502, {"detail": {"code": "load-failed", "message": "model"}})
    p = tmp_path / "a.wav"
    p.write_bytes(b"RIFF....")
    with pytest.raises(d.DiarizationError) as ei:
        d.diarize(str(p))
    assert ei.value.code == "load-failed"


def test_diarize_http_error_without_detail(monkeypatch, tmp_path):
    _patch(monkeypatch, 500, {})
    p = tmp_path / "a.wav"
    p.write_bytes(b"RIFF....")
    with pytest.raises(d.DiarizationError) as ei:
        d.diarize(str(p))
    assert ei.value.code == "service-error"


def test_detect_device_remote():
    assert d._detect_device() == "remote"


def test_normalise_speaker():
    assert d._normalise_speaker("A") == "SPEAKER_00"
    assert d._normalise_speaker("C") == "SPEAKER_02"
    assert d._normalise_speaker("SPEAKER_07") == "SPEAKER_07"
    assert d._normalise_speaker("") == "SPEAKER_00"
    # Change 126: CrispASR-Rohformate, die vorher still auf SPEAKER_00 fielen
    assert d._normalise_speaker("(speaker 0)") == "SPEAKER_00"
    assert d._normalise_speaker("(speaker 12)") == "SPEAKER_12"
    assert d._normalise_speaker("speaker 3") == "SPEAKER_03"
    assert d._normalise_speaker("3") == "SPEAKER_03"
    assert d._normalise_speaker("(Speaker 5)") == "SPEAKER_05"


def test_diarize_sendet_embedder_folgt_methode(monkeypatch, tmp_path):
    """Change 126: diarize_embedder erzwingt serverseitig das globale
    Speaker-Clustering — ohne gesendeten Wert lädt der Server nie einen
    Embedder und alle Labels bleiben chunk-lokal (Live-Befund: alles
    SPEAKER_00 bei 75-min-Meeting). Default-Methode ist foxnose → der
    WeSpeaker-Embedder wird gesendet."""
    fc = _patch(monkeypatch, 200, {"segments": []})
    p = tmp_path / "a.wav"
    p.write_bytes(b"RIFF....")
    d.diarize(str(p))
    data = fc.last_kwargs["data"]
    assert data["diarize_embedder"] == settings.DIARIZE_FOXNOSE_EMBEDDER
    assert data["diarize_embedder"]  # nicht leer


def test_diarize_pyannote_sendet_titanet_auto(monkeypatch, tmp_path):
    """pyannote → DIARIZE_EMBEDDER (Default 'auto' = TitaNet)."""
    fc = _patch(monkeypatch, 200, {"segments": []})
    p = tmp_path / "a.wav"
    p.write_bytes(b"RIFF....")
    d.diarize(str(p), method="pyannote")
    assert fc.last_kwargs["data"]["diarize_embedder"] == settings.DIARIZE_EMBEDDER


def test_diarize_foxnose_sendet_wespeaker(monkeypatch, tmp_path):
    """Change 126: foxnose braucht den WeSpeaker-Embedder (Registry-Alias
    'wespeaker', Auto-Download serverseitig) — nicht den TitaNet-Default."""
    fc = _patch(monkeypatch, 200, {"segments": []})
    p = tmp_path / "a.wav"
    p.write_bytes(b"RIFF....")
    d.diarize(str(p), method="foxnose")
    assert fc.last_kwargs["data"]["diarize_embedder"] == "wespeaker"
