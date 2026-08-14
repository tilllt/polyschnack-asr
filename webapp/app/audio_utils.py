"""Audio-Format-Politik + Dauer-Probing für Upload/URL-Import/Transcribe.

Storage-Policy (2026-08-14, User-Befund „Formate die WaveSurfer und
Transkriptionsmodelle nativ können, sollten wir nicht konvertieren"):
Formate, die der Browser (WaveSurfer) UND die ASR-Backends (ffmpeg-Decode
in approach-a, on-the-fly-WAV-Konvertierung für die übrigen) verarbeiten
können, werden UNKONVERTIERT gespeichert. Nur unbekannte/exotische Formate
werden beim Upload zu 16-kHz-mono-WAV konvertiert. WAV bleibt der
Fallback-Container für Backends ohne Compressed-Support (wird erst beim
Transkribieren erzeugt, nicht beim Upload).
"""
from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import Optional, Tuple

log = logging.getLogger(__name__)

TARGET_SR = 16000

#: Formate, die der Browser nativ abspielt UND ffmpeg dekodieren kann —
#: werden ohne Konvertierung gespeichert (WaveSurfer + ASR kommen damit klar).
NATIVE_AUDIO_EXTS = {
    ".wav", ".mp3", ".ogg", ".opus", ".webm", ".m4a", ".aac",
    ".flac", ".mpeg", ".mp4", ".oga", ".wma",
}


def is_native_audio(original_name: str) -> bool:
    return Path(original_name).suffix.lower() in NATIVE_AUDIO_EXTS


def prepare_storage(raw: bytes, original_name: str) -> Tuple[bytes, str, Optional[str]]:
    """Entscheide, ob das Original gespeichert oder konvertiert wird.

    Returns (audio_bytes, final_extension, conversion_note). Für native
    Formate: unverändert zurück, kein Hinweis. Sonst: 16-kHz-mono-WAV via
    ffmpeg (Fehler → HTTPException-artige RuntimeError-Meldung).
    """
    ext = Path(original_name).suffix.lower()
    if is_native_audio(original_name):
        return raw, ext, None
    return convert_to_wav_16k_mono(raw, original_name)


def convert_to_wav_16k_mono(raw: bytes, original_name: str) -> Tuple[bytes, str, Optional[str]]:
    """Immer-Konvertierung nach 16 kHz 16 bit mono WAV via ffmpeg (pipe).

    Wird für (a) exotische Upload-Formate und (b) Backends ohne
    Compressed-Support (on-the-fly beim Transkribieren) genutzt.
    """
    ext = Path(original_name).suffix.lower()
    log.info("Converting %s to 16kHz mono WAV", original_name)
    try:
        proc = subprocess.run(
            [
                "ffmpeg", "-y", "-nostdin",
                "-i", "pipe:0",
                "-ar", "16000", "-ac", "1", "-sample_fmt", "s16",
                "-f", "wav",
                "pipe:1",
            ],
            input=raw,
            capture_output=True,
            timeout=300,
        )
        if proc.returncode != 0:
            err = proc.stderr.decode("utf-8", errors="replace")[:500]
            raise RuntimeError(f"Konnte {original_name} nicht konvertieren: {err}")
        out = proc.stdout
        if not out:
            raise RuntimeError(f"Konnte {original_name} nicht konvertieren: leere Ausgabe")
        log.info("Converted %s: %d → %d bytes", original_name, len(raw), len(out))
        note = f"(konvertiert von {ext or 'unbekannt'} nach WAV)"
        return out, ".wav", note
    except subprocess.TimeoutExpired:
        raise RuntimeError(
            f"Konvertierung von {original_name} abgebrochen (länger als 300s)"
        ) from None


def probe_duration_s(audio_bytes: bytes, fallback_estimate: float = 0.0) -> float:
    """Exakte Dauer (Sekunden) via ffprobe — schnell, kein Voll-Decode.

    Fallback: übergebene Schätzung (oder 0). Die alte Größen-Schätzung
    (len/8000) war bei 128-kbps-MP3 um den Faktor 2 daneben — die
    VRAM-Prognose und die ETA hingen daran.
    """
    try:
        proc = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                "pipe:0",
            ],
            input=audio_bytes, capture_output=True, text=True, timeout=30,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            duration_s = float(proc.stdout.strip())
            if duration_s > 0:
                return duration_s
    except Exception:
        pass
    return fallback_estimate
