"""audio.py — M4A/MP4 mit trailing moov-Atom über Pipe dekodieren (2026-08-17).

Live-Befund: Signal-Sprachnachricht (M4A, moov-Atom bei ~98 % der Datei)
führte zu „ValueError: empty audio“ — ffmpeg kann nicht-seekbare Container
mit moov am Dateiende NICHT über stdin-Pipe lesen („partial file“, 0 Bytes).
Fix: _ffmpeg_decode fällt bei leerem/fehlerhaftem Pipe-Ergebnis auf eine
seekbare Temp-Datei zurück.

Die Test-Audio-Datei wird hier synthetisch mit ffmpeg erzeugt (moov ans
Ende geschrieben, ohne -movflags faststart) — derselbe Aufbau wie bei
Signal-/Handy-Aufnahmen.
"""
from __future__ import annotations

import os
import subprocess
import sys
import types

import numpy as np
import pytest

# audioop ist in Python 3.13 entfernt; der WAV-Pfad braucht es, der
# ffmpeg-Pfad nicht. Für diesen Test genügt ein Dummy.
if "audioop" not in sys.modules:
    sys.modules["audioop"] = types.ModuleType("audioop")

from polyschnack_service.audio import _ffmpeg_decode, load_audio

TARGET_SR = 16000


@pytest.fixture(scope="module")
def m4a_with_trailing_moov(tmp_path_factory) -> bytes:
    """Erzeugt ein echtes M4A mit moov-Atom am Dateiende (wie Signal).

    WICHTIG: ≥30 s Ton — kleinere Dateien passen komplett in den ffmpeg-
    Pipe-Puffer und scheitern NICHT über stdin (der Bug braucht eine Datei,
    die größer als der Puffer ist, live: 17 MB Signal-Sprachnachricht).
    """
    wav = tmp_path_factory.mktemp("audio") / "src.wav"
    out = tmp_path_factory.mktemp("audio") / "signal.m4a"
    # 30 s 440-Hz-Ton → WAV → M4A (AAC). OHNE -movflags faststart bleibt das
    # moov-Atom am Dateiende — der Pipe-Fall, den der Fix abdeckt.
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
    assert len(data) > 400_000, "Testdatei zu klein — Pipe-Fehler würde nicht reproduzieren"
    # moov-Atom wirklich am Ende? (Position > 90 % der Datei)
    moov_pos = data.rfind(b"moov")
    assert moov_pos > len(data) * 0.9, (
        f"moov at {moov_pos/len(data)*100:.1f}% — Testaufbau unbrauchbar"
    )
    return data


def test_ffmpeg_decode_pipe_fails_for_trailing_moov(m4a_with_trailing_moov):
    """Der ursprüngliche Pipe-only-Pfad scheitert bei trailing moov — das
    ist die Regression, die der Fix behebt (0 Samples via stdin)."""
    cmd = [
        "ffmpeg", "-nostdin", "-loglevel", "error",
        "-i", "pipe:0", "-ac", "1", "-ar", str(TARGET_SR), "-f", "s16le", "pipe:1",
    ]
    p = subprocess.run(cmd, input=m4a_with_trailing_moov,
                       capture_output=True, check=False)
    # Der alte Code hätte hier 0 Bytes bekommen → „empty audio“
    assert len(p.stdout) == 0


def test_load_audio_decodes_m4a_with_trailing_moov(m4a_with_trailing_moov):
    """Fix: load_audio liefert Samples statt leer (Temp-Datei-Fallback)."""
    wav = load_audio(m4a_with_trailing_moov)
    assert wav.size > 0
    assert wav.dtype == np.float32
    # 30 s bei 16 kHz → ~480 000 Samples (Toleranz für Codec-Delay)
    assert abs(wav.size / TARGET_SR - 30.0) < 0.5


def test_load_audio_still_decodes_plain_wav(tmp_path):
    """Kein Regressionsbruch: normale WAVs laufen weiter über den
    stdlib-Pfad (schnell, kein ffmpeg)."""
    import wave as wave_mod

    p = tmp_path / "tone.wav"
    with wave_mod.open(str(p), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(TARGET_SR)
        w.writeframes((np.sin(np.linspace(0, 440 * 2 * np.pi, TARGET_SR))
                       * 32767).astype("<i2").tobytes())
    wav = load_audio(p.read_bytes())
    assert wav.size == TARGET_SR  # exakt 1 s


def test_ffmpeg_decode_cleans_up_temp_files(m4a_with_trailing_moov, tmp_path, monkeypatch):
    """Temp-Dateien werden nach dem Fallback wieder gelöscht."""
    # Tempfile in ein kontrollierbares Verzeichnis lenken
    monkeypatch.setenv("TMPDIR", str(tmp_path))
    before = set(os.listdir(tmp_path))
    _ffmpeg_decode(m4a_with_trailing_moov)
    after = set(os.listdir(tmp_path))
    assert after == before  # nichts zurückgelassen
