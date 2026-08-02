"""Diarization-Parameter: num_speakers + min_duration_off (Sensitivität).

Punkte 1+2 des Parameter-Menüs:
1. Sprecheranzahl → num_speakers (min=max)
2. Sensitivität → min_duration_off (weniger Wechsel = höher)

Backend bekommt fertige pyannote-Werte; die Übersetzung der UI-Stufen
macht das Frontend.
"""
import pytest

from app.diarize import diarize

# ---------------------------------------------------------------------------
# diarize() reicht Parameter an die Pipeline durch
# ---------------------------------------------------------------------------


def test_diarize_reicht_num_speakers_durch(monkeypatch):
    calls = {}

    class FakePipeline:
        def __call__(self, path, **kwargs):
            calls["kwargs"] = kwargs
            return _fake_result()

    monkeypatch.setattr("app.diarize._load_pipeline", lambda: FakePipeline())

    diarize("/tmp/x.wav", num_speakers=2)
    assert calls["kwargs"].get("min_speakers") == 2
    assert calls["kwargs"].get("max_speakers") == 2


def test_diarize_reicht_min_duration_off_durch(monkeypatch):
    calls = {}

    class FakePipeline:
        def __call__(self, path, **kwargs):
            calls["kwargs"] = kwargs
            return _fake_result()

    monkeypatch.setattr("app.diarize._load_pipeline", lambda: FakePipeline())

    diarize("/tmp/x.wav", min_duration_off=0.4)
    assert calls["kwargs"].get("min_duration_off") == 0.4


def test_diarize_ohne_param_kein_min_duration_off(monkeypatch):
    """Default: kein min_duration_off → pyannote nutzt Pipeline-Default."""
    calls = {}

    class FakePipeline:
        def __call__(self, path, **kwargs):
            calls["kwargs"] = kwargs
            return _fake_result()

    monkeypatch.setattr("app.diarize._load_pipeline", lambda: FakePipeline())

    diarize("/tmp/x.wav")
    assert "min_duration_off" not in calls["kwargs"]
    assert "min_speakers" not in calls["kwargs"]


def _fake_result():
    """Minimales pyannote-3.x-Ergebnis (Annotation mit itertracks)."""

    class _Turn:
        start = 0.0
        end = 1.0

    class _Annotation:
        def itertracks(self, yield_label=False):
            return iter([(_Turn(), None, "SPEAKER_00")])

    return _Annotation()
