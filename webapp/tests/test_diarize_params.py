"""Diarization-Parameter (Option B): num_speakers → diarize_max_speakers.

Punkt 1 des Parameter-Menüs:
1. Sprecheranzahl → diarize_max_speakers (CrispASR-Feld, Upper Bound)

Bewusste Abweichung seit Option B: ``min_duration_off`` (Sensitivität) hat
in CrispASR keine direkte Entsprechung und wird NICHT übertragen —
nächster Hebel wäre diarize_cluster_threshold (anderes Semantikfeld).
"""
import httpx

from app.diarize import diarize
from app.config import settings


class _FakeClient:
    def __init__(self):
        self.last_kwargs = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def post(self, url, files=None, data=None):
        self.last_kwargs = {"url": url, "files": files, "data": data}
        return httpx.Response(200, json={"segments": []})


def _patch(monkeypatch):
    fc = _FakeClient()
    monkeypatch.setattr("app.diarize.httpx.Client", lambda *a, **k: fc)
    monkeypatch.setattr(settings, "DIAR_URL", "http://diar:8080")
    return fc


def test_diarize_reicht_max_speakers_durch(monkeypatch, tmp_path):
    fc = _patch(monkeypatch)
    p = tmp_path / "x.wav"
    p.write_bytes(b"RIFF....")
    diarize(str(p), num_speakers=2)
    assert fc.last_kwargs["data"]["diarize_max_speakers"] == "2"


def test_diarize_ohne_num_speakers_kein_feld(monkeypatch, tmp_path):
    fc = _patch(monkeypatch)
    p = tmp_path / "x.wav"
    p.write_bytes(b"RIFF....")
    diarize(str(p))
    assert "diarize_max_speakers" not in fc.last_kwargs["data"]


def test_diarize_min_duration_off_wird_nicht_uebertragen(monkeypatch, tmp_path):
    """CrispASR kennt kein min_duration_off — Parameter wird ignoriert."""
    fc = _patch(monkeypatch)
    p = tmp_path / "x.wav"
    p.write_bytes(b"RIFF....")
    diarize(str(p), min_duration_off=0.4)
    data = fc.last_kwargs["data"]
    assert "min_duration_off" not in data
    assert "diarize_cluster_threshold" not in data  # bewusst nicht gemappt
