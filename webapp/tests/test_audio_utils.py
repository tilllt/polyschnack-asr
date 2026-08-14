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
    class _R:
        returncode = 0
        stdout = b"wav-bytes"
        stderr = b""

    monkeypatch.setattr(au.subprocess, "run", lambda *a, **k: _R())
    out, ext, note = au.convert_to_wav_16k_mono(b"mp3", "a.mp3")
    assert out == b"wav-bytes"
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
