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
    _marker_suffix_trim,
    _strip_transcript_marker,
    _transcript_complete,
    _trim_marker_word_run,
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


# ——— Change 185: Suffix-Trim (chunked-Leak, gemischte End-Segmente) ———

_MARKER_EN = "Seven, four, two, eight, one, six, zero, three, nine"


def test_strip_chunked_langer_echter_text_mit_marker_suffix():
    """Change-185-Leak (Prod-Beleg REC 322, 941453a8): Chunked-Stream, das
    Marker-Suffix sitzt am Ende eines langen echten Segments (Ratio weit
    unter 0,5, Start lange vor dem Audio-Ende) — der alte Code hat hier
    NICHTS entfernt. Fix: Suffix-Trim, echter Text bleibt."""
    long_text = (
        "…klusive der Bildung komplett durchdringt und dadurch halt auch "
        "immer stattfinden muss und nicht optional ist. Das kann es nur sein, "
        "wenn man davon ausgeht, dass es irgendwann wieder verschwindet. Und "
        f"an dem Punkt sind wir, glaube ich, nicht mehr. {_MARKER_EN}."
    )
    segs = [_seg(0, 100, "Einleitung"), _seg(1575.6, 1643.9, long_text)]
    # audio_total_s inkl. Marker (8,1 s); Segment-Start liegt weit davor →
    # kein Zeit-Tail; nur der Suffix-Trim kann greifen.
    clean, text, found = _strip_transcript_marker(segs, long_text, 1644.2)
    assert found is True
    assert len(clean) == 2
    assert clean[-1]["start"] == 1575.6  # Timing unangetastet
    assert clean[-1]["end"] == 1643.9
    assert "nicht mehr." in clean[-1]["text"]
    assert "Seven" not in clean[-1]["text"]
    assert text.endswith("nicht mehr.")
    assert "nine" not in text.lower()


def test_strip_gemischtes_kurzes_segment_behaelt_echte_worte():
    """Prod-Beleg REC 318 (ec98bfdf): Kurzes gemischtes Segment mit Ratio
    >= 0,5 — der alte Code hätte es GANZ gepoppt („Okay. Dankeschön.
    Tschüss." verloren). Fix: nur das Marker-Suffix fällt, der Abschied
    bleibt im Segment."""
    seg_text = f"Okay. Dankeschön. Tschüss. {_MARKER_EN}."
    segs = [_seg(0, 100, "Gut, das waren die Fragen, die ich erstmal hatte."),
            _seg(393.48, 418.44, seg_text)]
    clean, text, found = _strip_transcript_marker(segs, "…Fragen. " + seg_text, None)
    assert found is True
    assert len(clean) == 2
    assert clean[-1]["text"] == "Okay. Dankeschön. Tschüss."
    assert clean[-1]["start"] == 393.48
    assert "seven" not in text.lower()


def test_suffix_trim_grossschreibung_und_interpunktion():
    """Marker wird mit Großschreibung/Interpunktion transkribiert
    („Seven, four, …") — Token-Match case-insensitiv + Satzzeichen-tolerant."""
    for phrase in (
        f"Das war es. {_MARKER_EN}.",
        f"Das war es. {_MARKER_EN.lower()}",
        "Das war es. 7 4 2 8 1 6 0 3 9",
        "Das war es. sieben vier zwei acht eins sechs null drei neun",
        "Das war es. Seven, Four, TWO, eight, ONE, six, zero, three, nine",
    ):
        clean, found = _marker_suffix_trim(phrase)
        assert found is True, phrase
        assert clean == "Das war es.", repr(clean)


def test_suffix_trim_keine_falschtreffer():
    """Einzelne Zahlen / kurze Läufe / Phrase nicht am Ende bleiben."""
    for keep in (
        "Die Antwort ist 42.",
        "Wir treffen uns um vier.",
        "Eins zwei drei, fertig los",          # 3er-Lauf < _MARKER_MIN_RUN
        "7 4 2 8 1 6 0 3 9 ist die Losnummer",  # nicht am Ende
        "und dann kamen sieben, vier, zwei Gäste",
    ):
        out, found = _marker_suffix_trim(keep)
        assert found is False, repr(keep)
        assert out == keep


def test_suffix_trim_reiner_marker_text():
    clean, found = _marker_suffix_trim(_MARKER_EN)
    assert found is True
    assert clean == ""


def test_strip_text_only_ohne_segmente():
    clean, text, found = _strip_transcript_marker([], f"ende {_MARKER_EN}", None)
    assert found is True
    assert text == "ende"


def test_trim_marker_word_run_entfernt_nur_marker_woerter():
    """Wort-Timing-Listen tragen den Marker (Bestands-Runs) — die
    Marker-Einträge fallen, echte Wörter + Timings der Wörter bleiben."""
    words = [
        {"start": 0.0, "end": 1.0, "word": "Okay."},
        {"start": 1.0, "end": 2.0, "word": "Dankeschön."},
        {"start": 2.0, "end": 3.0, "word": "Tschüss."},
    ] + [{"start": 10.0 + i, "end": 11.0 + i, "word": w}
         for i, w in enumerate(_MARKER_EN.split(", "))]
    clean, found = _trim_marker_word_run(words)
    assert found is True
    assert [x["word"] for x in clean] == ["Okay.", "Dankeschön.", "Tschüss."]
    assert clean[-1]["end"] == 3.0  # Timings der echten Wörter unangetastet


def test_trim_marker_word_run_keine_kurzen_laeufe():
    words = [{"start": 0.0, "end": 1.0, "word": "vier"},
             {"start": 1.0, "end": 2.0, "word": "Uhr"}]
    clean, found = _trim_marker_word_run(words)
    assert found is False
    assert clean == words
    assert _trim_marker_word_run([]) == ([], False)
    assert _trim_marker_word_run(None) == (None, False)


def test_strip_mischt_segment_words_werden_konsistent_getrimmt():
    """Segment-Rohbau mit words (Wort-Einträge unter 'word') — Text UND
    words-Liste werden getrimmt, echte Wörter bleiben."""
    seg_text = f"Okay. Dankeschön. Tschüss. {_MARKER_EN}."
    words = (
        [{"start": 393.5, "end": 395.0, "word": "Okay."},
         {"start": 395.5, "end": 397.0, "word": "Dankeschön."},
         {"start": 397.5, "end": 399.0, "word": "Tschüss."}]
        + [{"start": 400.0 + i, "end": 401.0 + i, "word": w}
           for i, w in enumerate(_MARKER_EN.split(", "))]
    )
    segs = [_seg(0, 100, "Einleitung"),
            {"start": 393.48, "end": 418.44, "text": seg_text, "words": words}]
    clean, _text, found = _strip_transcript_marker(segs, seg_text, None)
    assert found is True
    assert clean[-1]["text"] == "Okay. Dankeschön. Tschüss."
    assert [x["word"] for x in clean[-1]["words"]] == [
        "Okay.", "Dankeschön.", "Tschüss."
    ]
    assert clean[-1]["words"][-1]["end"] == 399.0


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


def test_append_marker_erzeugt_gueltige_16k_mono_wav():
    """Change 154: Der Concat-Output muss eine dekodierbare 16k/mono/s16-WAV
    sein — die alte aresample/pan-Filterkette erzeugte ein Format, das der
    ONNX-ASR nicht transkribieren konnte (leere Segmente)."""
    import io
    import wave as wave_mod

    out = _append_transcript_marker(_sine_wav(2.0))
    with wave_mod.open(io.BytesIO(out), "rb") as w:
        assert w.getnchannels() == 1
        assert w.getframerate() == 16000
        assert w.getsampwidth() == 2
        # ≈ 2,0 s Audio + 8,1 s Marker
        assert 9.5 <= w.getnframes() / 16000 <= 11.0


def test_append_marker_konvertiert_gemischte_inputs():
    """Change 154: Auch Stereo-/44,1-kHz-Inputs (typische Uploads) werden
    zu 16k/mono konvertiert — ffmpeg via Output-Flags, nicht via Filter."""
    import io
    import math
    import struct
    import wave as wave_mod

    bio = io.BytesIO()
    with wave_mod.open(bio, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(44100)
        n = int(1.0 * 44100)
        frames = bytearray()
        for i in range(n):
            v = int(12000 * math.sin(2 * math.pi * 440 * i / 44100))
            frames += struct.pack("<hh", v, v)  # Stereo
        w.writeframes(bytes(frames))
    stereo = bio.getvalue()

    out = _append_transcript_marker(stereo)
    assert out != stereo
    with wave_mod.open(io.BytesIO(out), "rb") as w:
        assert w.getnchannels() == 1
        assert w.getframerate() == 16000
        assert w.getsampwidth() == 2


def test_append_marker_leere_eingabe_unveraendert():
    assert _append_transcript_marker(b"") == b""
