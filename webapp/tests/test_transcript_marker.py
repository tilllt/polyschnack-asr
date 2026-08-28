"""Change 147: TTS-Marker für deterministische Vollständigkeits-Erkennung.

User-Befund 2026-08-28: 90-min-Film → nur 26,6 min transkribiert,
Status trotzdem done. User-Idee: Ein TTS-Marker (eindeutige Ziffernfolge)
wird ans Audio-Ende gehängt — taucht er im Transkript auf, hat die ASR
das Ende erreicht; fehlt er, brach der Stream ab. Kein Zeit-Raten, daher
auch korrekt für Filme mit stillem Abspann.
"""

import math
import wave
import io
import os

from app.service import (
    _append_transcript_marker,
    _is_marker_segment,
    _strip_transcript_marker,
    _TRANSCRIPT_MARKER_PATH,
)


def _segs(*texts: str) -> list:
    out = []
    for i, t in enumerate(texts):
        out.append({"start": i * 10.0, "end": i * 10.0 + 8.0, "text": t})
    return out


def _wav_16k(duration_s: float) -> bytes:
    rate = 16000
    frames = []
    n = int(duration_s * rate)
    for i in range(n):
        v = int(6000 * math.sin(2 * math.pi * 220 * i / rate))
        frames.append(v & 0xFF)
        frames.append((v >> 8) & 0xFF)
    bio = io.BytesIO()
    with wave.open(bio, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(bytes(frames))
    return bio.getvalue()


# ——— _is_marker_segment ———

def test_marker_als_ziffern_erkannt():
    assert _is_marker_segment("7 4 2 8 1 6 0 3 9")
    assert _is_marker_segment("7, 4, 2, 8, 1, 6, 0, 3, 9.")


def test_marker_als_zahlwoerter_erkannt():
    assert _is_marker_segment("seven four two eight one six zero three nine")


def test_normales_abschlusssegment_nicht_marker():
    assert not _is_marker_segment("das ist das ende des films")
    assert not _is_marker_segment("und so endet die geschichte hier")


def test_gemischtes_segment_mit_ziffern_nicht_marker():
    """Echtes Material mit einzelnen Ziffern darf nicht als Marker fallen."""
    assert not _is_marker_segment("er bekam 7 von 10 punkten")
    assert not _is_marker_segment("42 ist die antwort")


# ——— _strip_transcript_marker ———

def test_marker_segment_wird_entfernt():
    segs = _segs("hallo welt", "der film endet hier", "7 4 2 8 1 6 0 3 9")
    clean, text, found = _strip_transcript_marker(segs, "hallo welt der film endet hier 7 4 2 8 1 6 0 3 9")
    assert found
    assert len(clean) == 2
    assert text == "hallo welt der film endet hier"
    assert all("7" not in str(s.get("text")) for s in clean)


def test_ohne_marker_found_false():
    """Stream abgerissen → Marker fehlt → found=False (→ failed)."""
    segs = _segs("hallo welt", "der film endet hier")
    clean, text, found = _strip_transcript_marker(segs, "hallo welt der film endet hier")
    assert not found
    assert len(clean) == 2


def test_stiller_abspann_mit_marker_ist_ok():
    """User-Einwand: Film mit stillem Abspann — solange die ASR durchlief,
    IST der Marker transkribiert → found=True (vollständig)."""
    segs = _segs("hallo welt", "der film endet hier", "7 4 2 8 1 6 0 3 9")
    _, _, found = _strip_transcript_marker(segs, "hallo welt der film endet hier 7 4 2 8 1 6 0 3 9")
    assert found


def test_leere_und_kurze_eingaben():
    assert _strip_transcript_marker([], "") == ([], "", False)
    segs, _, found = _strip_transcript_marker(_segs("nur ein wort"), "nur ein wort")
    assert not found and len(segs) == 1


# ——— _append_transcript_marker (echter ffmpeg-Lauf) ———

def test_marker_wird_angehaengt():
    if not os.path.exists(_TRANSCRIPT_MARKER_PATH):
        import pytest
        pytest.skip("Marker-WAV fehlt im Repo")
    src = _wav_16k(3.0)
    out = _append_transcript_marker(src)
    # 3 s Audio + ~8 s Marker → Ergebnis deutlich länger als Eingabe
    assert len(out) > len(src) + 10000
