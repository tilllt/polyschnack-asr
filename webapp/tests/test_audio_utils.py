"""audio_utils: Storage-Policy (native Formate unkonvertiert), ffprobe-Dauer.

Regression 2026-08-14: alles wurde beim Upload zu 16-kHz-mono-WAV
konvertiert — unnötig für MP3/OGG/… (WaveSurfer + ASR dekodieren nativ)
und bei 150-min-Dateien ein 120-s-Timeout-Risiko am Upload.
"""
from __future__ import annotations

import subprocess

import pytest

from app import audio_utils as au


def test_prepare_storage_behaelt_native_formate():
    for name in ("audio.mp3", "song.ogg", "clip.webm", "a.m4a", "b.flac", "c.wav", "d.opus"):
        raw = b"id3" + name.encode()
        out, ext, note = au.prepare_storage(raw, name)
        assert out == raw, name
        assert ext == f".{name.rsplit('.', 1)[1]}", name
        assert note is None, name


def test_prepare_storage_konvertiert_exotisch(monkeypatch):
    calls = {}

    def fake_convert(raw, name):
        calls["raw"] = raw
        calls["name"] = name
        return b"wavdata", ".wav", "(konvertiert von .xyz nach WAV)"

    monkeypatch.setattr(au, "convert_to_wav_16k_mono", fake_convert)
    out, ext, note = au.prepare_storage(b"raw", "audio.xyz")
    assert out == b"wavdata"
    assert ext == ".wav"
    assert calls == {"raw": b"raw", "name": "audio.xyz"}


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


def test_convert_to_wav_16k_mono_timeout(monkeypatch):
    def _raise(*a, **k):
        raise subprocess.TimeoutExpired("ffmpeg", 300)

    monkeypatch.setattr(au.subprocess, "run", _raise)
    with pytest.raises(RuntimeError, match="300s"):
        au.convert_to_wav_16k_mono(b"mp3", "a.mp3")


def test_probe_duration_s_ffprobe(monkeypatch):
    class _R:
        returncode = 0
        stdout = "150.5\n"

    monkeypatch.setattr(au.subprocess, "run", lambda *a, **k: _R())
    assert au.probe_duration_s(b"x") == 150.5


def test_probe_duration_s_fallback(monkeypatch):
    monkeypatch.setattr(au.subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(FileNotFoundError()))
    assert au.probe_duration_s(b"x", fallback_estimate=42.0) == 42.0
