"""Change 011: M4A/MP4 mit moov-Atom am Ende → faststart-Remux beim Upload.

Live-Befund 2026-08-17: Signal-Sprachnachricht (17 MB M4A, moov bei 98,8 %)
→ Backend „ValueError: empty audio" (ffmpeg über Pipe kann trailing moov
nicht lesen). Lösung an der Wurzel: `prepare_storage` remuxt betroffene
Dateien beim Speichern mit `-c copy -movflags +faststart` — verlustfrei
(PCM byte-identisch), eine Kopie (die fällt beim Upload ohnehin an),
danach ist die Datei überall lesbar (Pipe, Player, Streaming).
"""
from __future__ import annotations

import subprocess

import pytest

from app import audio_utils as au


@pytest.fixture(scope="module")
def m4a_trailing_moov(tmp_path_factory) -> bytes:
    """Echtes M4A mit moov am Dateiende (≥30 s, sonst kein Pipe-Fehler)."""
    d = tmp_path_factory.mktemp("faststart")
    wav = d / "src.wav"
    out = d / "trailing.m4a"
    subprocess.run(
        ["ffmpeg", "-y", "-nostdin", "-loglevel", "error",
         "-f", "lavfi", "-i", "sine=frequency=440:duration=30",
         "-ar", "48000", "-ac", "1", str(wav)],
        check=True,
    )
    subprocess.run(
        ["ffmpeg", "-y", "-nostdin", "-loglevel", "error",
         "-i", str(wav), "-c:a", "aac", "-b:a", "128k", str(out)],
        check=True,
    )
    data = out.read_bytes()
    assert len(data) > 400_000, "zu klein — reproduziert den Pipe-Fehler nicht"
    return data


def test_moov_at_end_detects_trailing(m4a_trailing_moov):
    """moov-Atom am Dateiende wird erkannt (Bedingung für den Remux)."""
    assert au._moov_at_end(m4a_trailing_moov) is True


def test_moov_at_end_false_for_small_or_plain(m4a_trailing_moov):
    """Kleine Bytes / kein moov → False (kein Remux-Versuch)."""
    assert au._moov_at_end(b"") is False
    assert au._moov_at_end(b"abc") is False
    assert au._moov_at_end(b"x" * 200) is False


def test_prepare_storage_remuxes_trailing_moov(m4a_trailing_moov):
    """prepare_storage remuxt M4A mit trailing moov → moov vorne + Hinweis."""
    out, ext, note = au.prepare_storage(m4a_trailing_moov, "signal.m4a")
    assert ext == ".m4a"
    assert note == "(moov-Atom nach vorne geschrieben)"
    assert au._moov_at_end(out) is False
    pos = out.rfind(b"moov")
    assert 0 <= pos < len(out) * 0.01, f"moov bei {pos / len(out) * 100:.1f}%"


def test_remux_is_lossless(m4a_trailing_moov, tmp_path):
    """-c copy ist verlustfrei: PCM vorher == PCM nachher (byte-identisch).

    Vergleich über SEEKABLE Datei-Input (das Original ist über die Pipe
    nicht lesbar — 0 Bytes, genau der Bug — und daher unvergleichbar).
    """
    out, _, _ = au.prepare_storage(m4a_trailing_moov, "signal.m4a")

    def pcm(data: bytes) -> bytes:
        f_in = tmp_path / "in.m4a"
        f_in.write_bytes(data)
        p = subprocess.run(
            ["ffmpeg", "-nostdin", "-loglevel", "error",
             "-i", str(f_in), "-ac", "1", "-ar", "16000", "-f", "s16le", "pipe:1"],
            capture_output=True,
        )
        assert p.returncode == 0
        return p.stdout

    before = pcm(m4a_trailing_moov)
    after = pcm(out)
    assert len(before) > 0
    assert before == after


def test_remuxed_file_readable_over_pipe(m4a_trailing_moov):
    """Der eigentliche Bug: Original liefert über Pipe 0 Bytes, remuxt nicht."""
    out, _, _ = au.prepare_storage(m4a_trailing_moov, "signal.m4a")

    def pipe_bytes(data: bytes) -> int:
        p = subprocess.run(
            ["ffmpeg", "-nostdin", "-loglevel", "error",
             "-i", "pipe:0", "-ac", "1", "-ar", "16000", "-f", "s16le", "pipe:1"],
            input=data, capture_output=True,
        )
        return len(p.stdout)

    assert pipe_bytes(m4a_trailing_moov) == 0  # Vorher: Bug (0 Bytes)
    assert pipe_bytes(out) > 0  # Nachher: lesbar


def test_plain_native_files_not_remuxed():
    """M4A ohne trailing moov (z.B. MP3/faststart) bleibt unverändert."""
    raw = b"\x00\x00\x00\x18ftypM4A " + b"\x00" * 200  # kein moov am Ende
    out, ext, note = au.prepare_storage(raw, "a.m4a")
    assert out == raw
    assert note is None


def test_remux_failure_keeps_original(monkeypatch, m4a_trailing_moov):
    """Fehlgeschlagener Remux ist nicht-fatal: Original bleibt (Fallback)."""
    class _R:
        returncode = 1
        stdout = b""
        stderr = b"kaputt"

    monkeypatch.setattr(au.subprocess, "run", lambda *a, **k: _R())
    out, ext, note = au.prepare_storage(m4a_trailing_moov, "signal.m4a")
    assert out == m4a_trailing_moov
    assert note is None
