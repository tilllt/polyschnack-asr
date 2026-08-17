"""audio_utils: Storage-Policy (Browser-Matrix ehrlich), ffprobe-Dauer.

Rev. 2 (2026-08-14): Nur Formate, die ALLE Browser inkl. Safari/iOS nativ
abspielen, werden unkonvertiert gespeichert (WAV/MP3/M4A/MP4/FLAC). Alles
andere — .aac (ADTS, kein Browser), .ogg/.opus (Safari kann kein Ogg),
.webm, .wma — wird beim Upload nach MP3 128k mono konvertiert.
"""

from __future__ import annotations

import subprocess

import pytest

from app import audio_utils as au


def test_prepare_storage_behaelt_native_formate():
    for name in ("audio.mp3", "a.m4a", "book.m4b", "b.flac", "c.wav", "clip.mp4"):
        raw = b"id3" + name.encode()
        out, ext, note = au.prepare_storage(raw, name)
        assert out == raw, name
        assert ext == f".{name.rsplit('.', 1)[1]}", name
        assert note is None, name


def test_prepare_storage_konvertiert_browser_inkompatibel(monkeypatch):
    """aac/ogg/opus/webm/wma sind NICHT browser-nativ → MP3-Transcode."""
    calls = []

    def fake_convert(raw, name):
        calls.append(name)
        return b"mp3data", ".mp3", "(konvertiert von X nach MP3)"

    monkeypatch.setattr(au, "convert_to_mp3", fake_convert)
    for name in ("voice.aac", "song.ogg", "d.opus", "clip.webm", "old.wma", "x.aiff", "y.amr"):
        out, ext, note = au.prepare_storage(b"raw", name)
        assert out == b"mp3data", name
        assert ext == ".mp3", name
    assert calls == ["voice.aac", "song.ogg", "d.opus", "clip.webm", "old.wma", "x.aiff", "y.amr"]


def test_convert_to_mp3_ok(monkeypatch):
    class _R:
        returncode = 0
        stdout = b"mp3-bytes"
        stderr = b""

    monkeypatch.setattr(au.subprocess, "run", lambda *a, **k: _R())
    out, ext, note = au.convert_to_mp3(b"wav", "a.aac")
    assert out == b"mp3-bytes"
    assert ext == ".mp3"
    assert "nach MP3" in (note or "")


def test_convert_to_mp3_fehler(monkeypatch):
    class _R:
        returncode = 1
        stdout = b""
        stderr = b"kaputt"

    monkeypatch.setattr(au.subprocess, "run", lambda *a, **k: _R())
    with pytest.raises(RuntimeError, match="kaputt"):
        au.convert_to_mp3(b"wav", "a.aac")


def test_convert_to_mp3_timeout(monkeypatch):
    def _raise(*a, **k):
        raise subprocess.TimeoutExpired("ffmpeg", 600)

    monkeypatch.setattr(au.subprocess, "run", _raise)
    with pytest.raises(RuntimeError, match="600s"):
        au.convert_to_mp3(b"wav", "a.aac")


def test_convert_to_wav_16k_mono_ok(monkeypatch):
    # Echtes Mini-WAV (1 Sample), damit der Pipe-Pfad als erfolgreich gilt —
    # seit Fix 2026-08-17 prüft die Funktion auf echten Audio-Inhalt
    # (_wav_has_audio), Header-only-Bytes würden den Temp-File-Fallback triggern.
    def _mini_wav() -> bytes:
        return (
            b"RIFF" + (44).to_bytes(4, "little") + b"WAVE"
            + b"fmt " + (16).to_bytes(4, "little")
            + (1).to_bytes(2, "little") + (1).to_bytes(2, "little")
            + (16000).to_bytes(4, "little") + (32000).to_bytes(4, "little")
            + (2).to_bytes(2, "little") + (16).to_bytes(2, "little")
            + b"data" + (2).to_bytes(4, "little") + b"\x00\x00"
        )

    class _R:
        returncode = 0
        stdout = _mini_wav()
        stderr = b""

    monkeypatch.setattr(au.subprocess, "run", lambda *a, **k: _R())
    out, ext, note = au.convert_to_wav_16k_mono(b"mp3", "a.mp3")
    assert out == _mini_wav()
    assert ext == ".wav"
    assert "konvertiert" in (note or "")


def test_convert_to_wav_16k_mono_fehler(monkeypatch):
    class _R:
        returncode = 1
        stdout = b""
        stderr = b"boom"

    monkeypatch.setattr(au.subprocess, "run", lambda *a, **k: _R())
    with pytest.raises(RuntimeError, match="boom"):
        au.convert_to_wav_16k_mono(b"mp3", "a.mp3")


def test_probe_duration_s_ffprobe(monkeypatch):
    class _R:
        returncode = 0
        stdout = b"150.5\n"

    monkeypatch.setattr(au.subprocess, "run", lambda *a, **k: _R())
    assert au.probe_duration_s(b"x") == 150.5


def test_probe_duration_s_fallback(monkeypatch):
    monkeypatch.setattr(au.subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(FileNotFoundError()))
    assert au.probe_duration_s(b"x", fallback_estimate=42.0) == 42.0


def test_probe_duration_path_echt_ffprobe(tmp_path):
    """Echter ffprobe-Aufruf auf Dateien (kein Mock) — WAV (Header) und MP3
    (Frame-basiert) müssen die echte Dauer liefern, nicht den Fallback."""
    import shutil

    if shutil.which("ffprobe") is None:
        pytest.skip("ffprobe nicht verfügbar")

    wav = tmp_path / "t.wav"
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi",
         "-i", "sine=frequency=440:duration=2", "-ar", "16000", "-ac", "1", str(wav)],
        check=True,
    )
    d = au.probe_duration_path(wav)
    assert d is not None and 1.9 <= d <= 2.2, f"WAV-Dauer falsch: {d}"

    mp3 = tmp_path / "t.mp3"
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi",
         "-i", "sine=frequency=440:duration=2", "-b:a", "128k", str(mp3)],
        check=True,
    )
    d2 = au.probe_duration_path(mp3)
    assert d2 is not None and 1.9 <= d2 <= 2.5, f"MP3-Dauer falsch: {d2}"


def test_probe_duration_path_fehlt_gibt_none(tmp_path):
    assert au.probe_duration_path(tmp_path / "gibt-es-nicht.mp3") is None


# ============================================================
# M4A trailing moov → convert_to_wav_16k_mono (Fix 2026-08-17)
# ============================================================
def _make_trailing_moov_m4a(tmp_path, duration_s: int = 40):
    """Erzeugt eine echte M4A mit moov-Atom am Dateiende (> 90 %).

    ffmpeg schreibt ohne +faststart das moov-Atom ans Dateiende — genau das
    Smartphone/Signal-Muster. Muss ≥ 30 s / > ~400 KB sein, sonst passt die
    Datei in den ffmpeg-Pipe-Puffer und reproduziert das Problem NICHT
    (Skill-Referenz m4a-trailing-moov-pipe-decode.md).
    """
    import shutil

    if shutil.which("ffmpeg") is None:
        pytest.skip("ffmpeg nicht verfügbar")

    out = tmp_path / f"trailing_{duration_s}s.m4a"
    subprocess.run(
        [
            "ffmpeg", "-y", "-loglevel", "error",
            "-f", "lavfi", "-i", f"sine=frequency=440:duration={duration_s}",
            "-c:a", "aac", "-b:a", "128k", str(out),
        ],
        check=True,
    )
    data = out.read_bytes()
    assert len(data) > 400_000, f"Testdatei zu klein ({len(data)} B) — beweist nichts"
    moov_frac = data.rfind(b"moov") / len(data)
    assert moov_frac > 0.9, f"moov nicht am Dateiende ({moov_frac:.1%})"
    return data, out.name


def test_convert_m4a_trailing_moov_liefert_echtes_wav(tmp_path):
    """M4A mit moov am Ende → valides WAV mit data-Chunk > 0 (nicht 78 B).

    Regression für den Live-Befund 2026-08-17 (Recording 386c71e2…):
    `ffmpeg -i pipe:0` liefert bei trailing-moov-M4A returncode 0, aber nur
    den WAV-Header (78 Bytes, 0 Frames) → Diar-Service: "failed to read the
    frames of the audio data". Der Fix muss auf eine seekbare Temp-Datei
    zurückfallen.
    """
    raw, name = _make_trailing_moov_m4a(tmp_path)
    wav, ext, note = au.convert_to_wav_16k_mono(raw, name)
    assert ext == ".wav"
    assert au._wav_has_audio(wav), f"kein echtes WAV ({len(wav)} B): {note}"
    # 40 s @ 16 kHz mono s16 ≈ 1,28 MB — Header-only (78 B) wäre ein Bruchteil
    assert len(wav) > 1_000_000, f"WAV zu klein ({len(wav)} B) — Audio fehlt"


def test_wav_has_audio_erkennt_header_only():
    """78-Byte-Header-only-WAV (returncode-0-Falle) → False."""
    # Minimal-WAV: RIFF/WAVE + fmt + data mit Größe 0
    header_only = (
        b"RIFF" + (36).to_bytes(4, "little") + b"WAVE"
        + b"fmt " + (16).to_bytes(4, "little")
        + (1).to_bytes(2, "little") + (1).to_bytes(2, "little")
        + (16000).to_bytes(4, "little") + (32000).to_bytes(4, "little")
        + (2).to_bytes(2, "little") + (16).to_bytes(2, "little")
        + b"data" + (0).to_bytes(4, "little")
    )
    assert not au._wav_has_audio(header_only)
    assert not au._wav_has_audio(b"")
    assert not au._wav_has_audio(b"RIFFxxxxWAVE")  # zu kurz / kein data
    # ffmpeg-Pipe-Platzhalter 0xFFFFFFFF (Live-Befund 2026-08-17: 78 B) → False,
    # wenn NICHTS nach dem data-Header folgt (Header-only)
    placeholder = header_only[:-8] + b"data" + b"\xff\xff\xff\xff"
    assert not au._wav_has_audio(placeholder)
    # …aber True, wenn echte Frames folgen (ffmpeg schreibt den Platzhalter
    # bei Pipe-Ausgabe auch bei gültiger Konvertierung — Datei mit 44 B Frames)
    placeholder_frames = placeholder + b"\x00" * 44
    assert au._wav_has_audio(placeholder_frames)
    # data-Größe passt nicht in die Gesamtlänge (abgeschnitten) → False
    truncated = header_only[:-8] + b"data" + (1000).to_bytes(4, "little") + b"\x00\x00"
    assert not au._wav_has_audio(truncated)
    # echtes WAV mit 1 Sample → True
    real = header_only[:-8] + b"data" + (2).to_bytes(4, "little") + b"\x00\x00"
    assert au._wav_has_audio(real)
