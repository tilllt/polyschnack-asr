"""Audio-Format-Politik + Dauer-Probing für Upload/URL-Import/Transcribe.

Storage-Policy (2026-08-14, Rev. 2 — Browser-Matrix ehrlich):
Nur Formate, die ALLE relevanten Browser inkl. Safari/iOS nativ im
<audio>-Element abspielen, werden UNKONVERTIERT gespeichert: WAV, MP3,
M4A/MP4 (AAC), FLAC. Alles andere wird beim Upload nach MP3 (128 kbit/s,
mono) konvertiert — darunter .aac (roher ADTS-AAC: KEIN Browser kann das),
.ogg/.oga/.opus (Ogg-Container: Safari/iOS können kein Ogg), .webm
(Safari/iOS eingeschränkt), .wma (kein Browser), .aiff (Chrome/Firefox
nicht), .amr/.caf/.3gp/.ape u.ä.

Gründe für MP3 statt 16-kHz-WAV als Transcode-Ziel: MP3 ist überall
abspielbar, klein (~57 MB statt ~690 MB bei 6 h) und die ASR-Backends
bekommen ihre 16-kHz-WAV sowieso on-the-fly (Backends ohne
Compressed-Support). WAV bleibt nur der on-the-fly-Zwischencontainer beim
Transkribieren.
"""
from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import Optional, Tuple

log = logging.getLogger(__name__)

TARGET_SR = 16000

#: Formate, die der Browser (inkl. Safari/iOS) NATIV abspielt UND ffmpeg
#: dekodieren kann — werden ohne Konvertierung gespeichert.
#: Ehrliche Matrix: .aac (ADTS) kann kein Browser, .ogg/.opus/.webm kann
#: Safari/iOS nicht, .wma kann praktisch nichts — die werden konvertiert.
NATIVE_AUDIO_EXTS = {
    ".wav", ".mp3", ".m4a", ".m4b", ".mp4", ".flac",
}


def is_native_audio(original_name: str) -> bool:
    return Path(original_name).suffix.lower() in NATIVE_AUDIO_EXTS


def prepare_storage(raw: bytes, original_name: str) -> Tuple[bytes, str, Optional[str]]:
    """Entscheide, ob das Original gespeichert oder konvertiert wird.

    Returns (audio_bytes, final_extension, conversion_note). Für native
    Formate: unverändert zurück, kein Hinweis. Sonst: MP3 128k mono via
    ffmpeg (Fehler → RuntimeError-Meldung).
    """
    ext = Path(original_name).suffix.lower()
    if is_native_audio(original_name):
        return raw, ext, None
    return convert_to_mp3(raw, original_name)


def convert_to_mp3(raw: bytes, original_name: str) -> Tuple[bytes, str, Optional[str]]:
    """Immer-Konvertierung nach MP3 128 kbit/s mono via ffmpeg (pipe).

    Transcode-Ziel für alles, was der Browser nicht nativ abspielt
    (siehe Modul-Docstring). Klein (~57 MB bei 6 h) und überall
    abspielbar; ASR-Backends bekommen ihre 16-kHz-WAV on-the-fly.
    """
    ext = Path(original_name).suffix.lower()
    log.info("Converting %s to MP3 128k mono", original_name)
    try:
        proc = subprocess.run(
            [
                "ffmpeg", "-y", "-nostdin",
                "-i", "pipe:0",
                "-vn", "-ac", "1", "-ar", "44100", "-b:a", "128k",
                "-f", "mp3",
                "pipe:1",
            ],
            input=raw,
            capture_output=True,
            timeout=600,
        )
        if proc.returncode != 0:
            err = proc.stderr.decode("utf-8", errors="replace")[:500]
            raise RuntimeError(f"Konnte {original_name} nicht konvertieren: {err}")
        out = proc.stdout
        if not out:
            raise RuntimeError(f"Konnte {original_name} nicht konvertieren: leere Ausgabe")
        log.info("Converted %s: %d → %d bytes", original_name, len(raw), len(out))
        note = f"(konvertiert von {ext or 'unbekannt'} nach MP3)"
        return out, ".mp3", note
    except subprocess.TimeoutExpired:
        raise RuntimeError(
            f"Konvertierung von {original_name} abgebrochen (länger als 600s)"
        ) from None


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
    """Dauer via ffprobe über Pipe — NUR Fallback-Nutzung!

    Fix 2026-08-14: `input=bytes` + `text=True` crashte (AttributeError)
    und der Fehler wurde verschluckt → es galt IMMER der Größen-Fallback
    (bei 128-kbps-MP3 um Faktor 2 daneben). Der Aufruf ist jetzt
    bytes-korrekt, aber ffprobe liefert über nicht-seekbare Pipes oft
    „N/A" — für präzise Dauern `probe_duration_path` (Datei) verwenden.
    """
    try:
        proc = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                "pipe:0",
            ],
            input=audio_bytes, capture_output=True, timeout=30,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            duration_s = float(proc.stdout.decode("utf-8", errors="replace").strip())
            if duration_s > 0:
                return duration_s
    except Exception:
        pass
    return fallback_estimate


def probe_duration_path(path: Path) -> Optional[float]:
    """Exakte Dauer (Sekunden) einer Datei via ffprobe — zuverlässig.

    Datei-basiert (seekbar), im Gegensatz zur Pipe-Variante, die bei
    nicht-seekbarem Input oft „N/A" liefert. WAV: aus dem Header; MP3:
    Frame-Zählung. Rückgabe None bei Fehler — der Aufrufer entscheidet
    über den Fallback.
    """
    try:
        proc = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            capture_output=True, timeout=30,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            duration_s = float(proc.stdout.decode("utf-8", errors="replace").strip())
            if duration_s > 0:
                return duration_s
    except Exception:
        pass
    return None
