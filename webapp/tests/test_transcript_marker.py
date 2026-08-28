"""Change 147: TTS-Marker für deterministische Vollständigkeits-Erkennung.

User-Befund 2026-08-28: 90-min-Film → nur 26,6 min transkribiert,
Status trotzdem done. User-Idee: Ein TTS-Marker (eindeutige Ziffernfolge)
wird ans Audio-Ende gehängt. Die Erkennung ist ZEIT-basiert: Wurde der
Marker transkribiert, existieren Segmente nach der echten Audiodauer.
Fehlt er, hat die ASR das Audio-Ende nicht erreicht (Stream abgerissen).
"""

import subprocess as sp

from app.service import (
    _append_transcript_marker,
    _marker_ratio,
    _strip_transcript_marker,
    _transcript_complete,
    _TRANSCRIPT_MARKER_S,
    _MARKER_TAIL_S,
)


def _seg(start, end, text):
    return {"start": start, "end": end, "text": text, "words": []}


# ——— _transcript_complete (Zeit-Prüfung) ———

def test_complete_nahe_am_ende_ist_fertig():
    # Audio mit Marker: 5371 + 8 s; letztes Segment endet kurz vor dem
    # markerverlängerten Ende → ASR hat das Ende erreicht (z.B. stille
    # letzte Sekunden des Films + Marker).
    segs = [_seg(0, 1596, "Hallo"), _seg(1600, 5375.0, "Ende")]
    assert _transcript_complete(segs, 5371.0 + _TRANSCRIPT_MARKER_S) is True


def test_complete_abspann_mit_marker_ist_fertig():
    # 90-min-Film, letzte echte Wörter bei 88 min, dann 2 min Stille +
    # Marker — der Marker wurde transkribiert (Segment nach der echten
    # Dauer) → vollständig. Das ist der User-Einwand gegen reine
    # Zeit-Toleranzen: langer stiller Abspann ist OK.
    total = 5371.0 + _TRANSCRIPT_MARKER_S
    segs = [_seg(0, 5280, "letzte worte"), _seg(5371.0, total, "7 4 2 8 1 6 0 3 9")]
    assert _transcript_complete(segs, total) is True


def test_complete_stream_abgerissen_ist_unvollstaendig():
    # User-Befund: letztes Segment endet bei 26,6 min (1596 s), Audio
    # ist 89,5 min + Marker → unvollständig.
    total = 5371.0 + _TRANSCRIPT_MARKER_S
    segs = [_seg(0, 1596, "…nur der Anfang")]
    assert _transcript_complete(segs, total) is False


def test_complete_ohne_dauer_keine_aussage():
    assert _transcript_complete([_seg(0, 100, "x")], None) is True


# ——— _strip_transcript_marker (Entfernung + found) ———

def test_strip_entfernt_marker_segment():
    total = 5371.0 + _TRANSCRIPT_MARKER_S
    segs = [_seg(0, 1596, "Hallo welt"), _seg(5371.0, total, "7 4 2 8 1 6 0 3 9")]
    clean, text, found = _strip_transcript_marker(segs, "Hallo welt 7 4 2 8 1 6 0 3 9", total)
    assert found is True
    assert len(clean) == 1
    assert text == "Hallo welt"
    assert clean[0]["start"] == 0


def test_strip_entfernt_ziffern_segment_ohne_zeitbasis():
    # Auch ohne verlässliche Dauer (audio_total_s=None) werden reine
    # Ziffern-Segmente entfernt (Inhalt-Heuristik als Fallback).
    segs = [_seg(0, 10, "das ende"), _seg(10, 18, "7 4 2 8 1 6 0 3 9")]
    clean, text, found = _strip_transcript_marker(segs, "das ende 7 4 2 8 1 6 0 3 9", None)
    assert found is True
    assert text == "das ende"
    assert len(clean) == 1


def test_strip_laesst_normales_ende_unangetastet():
    segs = [_seg(0, 5280, "und so endet die geschichte")]
    clean, text, found = _strip_transcript_marker(segs, "und so endet die geschichte", 5371.0)
    assert found is False
    assert clean == segs


def test_strip_normales_ende_mit_ziffern_bleibt():
    # Ein echtes Ende mit einer einzelnen Zahl („42") wird NICHT als
    # Marker entfernt (zu wenig Treffer).
    segs = [_seg(0, 100, "die antwort ist 42")]
    clean, _, found = _strip_transcript_marker(segs, "die antwort ist 42", 200.0)
    assert found is False
    assert len(clean) == 1


# ——— _marker_ratio ———

def test_marker_ratio_ziffern_und_woerter():
    assert _marker_ratio("7 4 2 8 1 6 0 3 9") == 1.0
    assert _marker_ratio("seven four two eight one six zero three nine") == 1.0
    assert _marker_ratio("das ist das ende") == 0.0
    assert _marker_ratio("die antwort ist 42") == 1 / 4


# ——— _append_transcript_marker (ffmpeg, echte Bytes) ———

def _sine_wav(seconds: float, freq: int = 440, rate: int = 16000) -> bytes:
    import math
    import struct

    bio = __import__("io").BytesIO()
    import wave

    with wave.open(bio, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        frames = bytearray()
        n = int(seconds * rate)
        for i in range(n):
            v = int(12000 * math.sin(2 * math.pi * freq * i / rate))
            frames.append(v & 0xFF)
            frames.append((v >> 8) & 0xFF)
        w.writeframes(bytes(frames))
    return bio.getvalue()


def test_append_marker_verlaengert_audio():
    wav = _sine_wav(2.0)
    out = _append_transcript_marker(wav)
    assert out != wav
    # Marker-Dauer ist bekannt; das Ergebnis ist länger (16k WAV: 2 s +
    # 8,1 s ≈ 10,1 s → ≥ 350 KB bei 16k/mono/s16).
    assert len(out) > 300_000


def test_append_marker_leere_eingabe_unveraendert():
    assert _append_transcript_marker(b"") == b""
