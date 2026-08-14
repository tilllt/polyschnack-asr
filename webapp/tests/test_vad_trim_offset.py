"""VAD-Trim-Offset (2026-08-14, User-Befund „Klick spielt falschen Ton").

trim_silence_with_offset muss (getrimmte_bytes, offset_s) liefern, und
service._shift_segments verschiebt Segment-/Wort-Timestamps um den Offset,
damit sie zur Originaldatei passen (das Playback nutzt das Original,
ASR/Aligner liefen auf dem getrimmten Audio).
"""
from __future__ import annotations

import io
import wave

import numpy as np
import pytest

from app import service
from app import vad


def _make_wav(duration_s: float = 3.0, sr: int = 16000) -> bytes:
    """3 s WAV: 1 s Stille + 1 s Ton + 1 s Stille."""
    t = np.arange(int(duration_s * sr), dtype=np.float32) / sr
    # Ton nur in der Mitte (1s..2s)
    tone = 0.5 * np.sin(2 * np.pi * 440 * t)
    tone[: sr] = 0.0
    tone[-sr:] = 0.0
    s16 = (tone * 32767).astype("<i2").tobytes()
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(s16)
    return buf.getvalue()


# ------------------------------------------------- trim_silence_with_offset

def test_trim_with_offset_liefert_getrimmt_und_offset(monkeypatch):
    monkeypatch.setattr(
        vad, "detect_speech_regions",
        lambda *a, **k: [{"start": 1.0, "end": 2.0}],
    )
    out, offset = vad.trim_silence_with_offset(_make_wav())
    assert offset == pytest.approx(1.0)
    assert out != _make_wav()
    # getrimmt = nur die 1 s Ton
    with wave.open(io.BytesIO(out)) as w:
        assert w.getnframes() / w.getframerate() == pytest.approx(1.0)


def test_trim_ohne_regionen_kein_offset(monkeypatch):
    monkeypatch.setattr(vad, "detect_speech_regions", lambda *a, **k: [])
    raw = _make_wav()
    out, offset = vad.trim_silence_with_offset(raw)
    assert out == raw
    assert offset == 0.0


def test_trim_voller_bereich_kein_offset(monkeypatch):
    # Region deckt das ganze Audio ab → nichts zu trimmen
    monkeypatch.setattr(
        vad, "detect_speech_regions",
        lambda *a, **k: [{"start": 0.0, "end": 3.0}],
    )
    raw = _make_wav()
    out, offset = vad.trim_silence_with_offset(raw)
    assert out == raw
    assert offset == 0.0


def test_trim_silence_wrapper_kompatibel(monkeypatch):
    """Der alte Wrapper liefert weiterhin nur bytes (Rückwärtskompatibilität)."""
    monkeypatch.setattr(
        vad, "detect_speech_regions",
        lambda *a, **k: [{"start": 1.0, "end": 2.0}],
    )
    out = vad.trim_silence(_make_wav())
    assert isinstance(out, bytes)


# ------------------------------------------------------ _shift_segments

def test_shift_segments_verschiebt_alles():
    segments = [
        {"start": 10.0, "end": 11.0,
         "words": [{"start": 10.2, "end": 10.5}, {"start": 10.6, "end": 10.9}]},
        {"start_ms": 12000.0, "end_ms": 13000.0,
         "words": [{"start": 12.5, "end": 12.8}]},
    ]
    service._shift_segments(segments, 2.5)
    assert segments[0]["start"] == pytest.approx(12.5)
    assert segments[0]["end"] == pytest.approx(13.5)
    assert segments[0]["words"][0]["start"] == pytest.approx(12.7)
    assert segments[1]["start_ms"] == pytest.approx(14500.0)
    assert segments[1]["end_ms"] == pytest.approx(15500.0)
    assert segments[1]["words"][0]["start"] == pytest.approx(15.0)


def test_shift_segments_null_offset_unveraendert():
    segments = [{"start": 1.0, "end": 2.0, "words": [{"start": 1.1, "end": 1.2}]}]
    service._shift_segments(segments, 0.0)
    assert segments[0]["start"] == 1.0
    assert segments[0]["words"][0]["start"] == 1.1
