"""Change 146: Erkennung still abgerissener ASR-Streams.

User-Befund 2026-08-28: 90-min-Film → nur 26,6 min transkribiert,
Status trotzdem done (Backend schließt die SSE-Verbindung oft ohne
error-Event).
"""
import pytest

from app.service import _detect_truncated_asr, _probe_audio_duration

DUR = 5371.9  # 89,5 min


def _segs(last_end: float) -> list:
    return [{"start": 0.0, "end": last_end / 2, "text": "a"},
            {"start": last_end / 2, "end": last_end, "text": "b"}]


def test_vollstaendig_kein_fehler():
    """Letztes Segment ≈ Audio-Ende → kein Fehler."""
    assert _detect_truncated_asr(_segs(DUR - 5.0), DUR) is None


def test_leichte_abweichung_innen_toleranz():
    assert _detect_truncated_asr(_segs(DUR - 25.0), DUR) is None


def test_still_abgerissen_wird_erkannt():
    """26,6 min von 89,5 min → Fehlermeldung (der User-Befund)."""
    msg = _detect_truncated_asr(_segs(1596.0), DUR)
    assert msg is not None
    assert "26 von 89 min" in msg
    assert "ASR-Verbindung abgebrochen" in msg


def test_keine_segmente_kein_fehler():
    assert _detect_truncated_asr([], DUR) is None


def test_ohne_dauer_aber_mit_audio_probe(tmp_path, monkeypatch):
    """Fällt auf ffprobe zurück, wenn keine Dauer übergeben wurde."""
    import app.service as svc

    monkeypatch.setattr(svc, "_probe_audio_duration", lambda b: DUR)
    msg = _detect_truncated_asr(_segs(100.0), None, b"fake-audio")
    assert msg is not None
    assert "1 von 89 min" in msg


def test_probe_audio_duration_mit_echtem_wav(tmp_path):
    """ffprobe auf eine synthetische WAV → korrekte Dauer."""
    import subprocess

    if not __import__("shutil").which("ffprobe"):
        pytest.skip("ffprobe nicht installiert")
    wav = tmp_path / "t.wav"
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
         "sine=frequency=440:duration=2.0", "-ar", "16000", "-ac", "1",
         str(wav)], check=True, capture_output=True,
    )
    d = _probe_audio_duration(wav.read_bytes())
    assert d is not None and 1.9 < d < 2.1
