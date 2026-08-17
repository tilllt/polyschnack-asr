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
import os
import subprocess
import tempfile
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


def _moov_at_end(data: bytes) -> bool:
    """True, wenn ein MP4/M4A moov-Atom am Dateiende liegt (nicht faststart).

    Signal-/Handy-Aufnahmen schreiben moov ans Ende — dann können
    nicht-seekbare Leser (ffmpeg über stdin-Pipe, Streaming-Player)
    die Datei NICHT lesen („partial file", 0 Bytes → „empty audio").
    Position > 50 % der Datei gilt als „am Ende" (faststart-Dateien
    haben moov direkt nach ftyp bei < 1 %).
    """
    if len(data) < 100:
        return False
    pos = data.rfind(b"moov")
    if pos < 0:
        return False
    return pos > len(data) * 0.5


def _faststart_remux(raw: bytes, original_name: str) -> Tuple[bytes, str, Optional[str]]:
    """moov-Atom an den Dateianfang verschieben — OHNE Re-Encode.

    ``ffmpeg -c copy -movflags +faststart`` schreibt nur die Container-
    Boxen neu (kein Audio-Re-Encode: verlustfrei, CPU-kostenlos, die
    AAC-Samples werden 1:1 durchgereicht).

    WICHTIG: faststart braucht eine SEEKABLE Ausgabe (ffmpeg schreibt
    moov ans Ende und korrigiert dann die Offsets) — pipe:1 schlägt
    fehl. Deshalb Temp-Dateien: die eine Kopie fällt beim Upload
    ohnehin an (Storage), NICHT bei jeder Transkription. Für
    5-GB-Dateien: einmalige I/O beim Speichern, danach ist die Datei
    überall lesbar (Backend, Player, Streaming) — kein Workaround mehr
    im Backend nötig.
    """
    import tempfile

    ext = Path(original_name).suffix.lower()
    log.info("faststart: moov-Atom am Ende (%s) → remuxe nach vorne", original_name)
    tmp_in = tmp_out = None
    try:
        with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tf:
            tf.write(raw)
            tmp_in = tf.name
        with tempfile.NamedTemporaryFile(suffix=".out" + ext, delete=False) as tf2:
            tmp_out = tf2.name
        proc = subprocess.run(
            [
                "ffmpeg", "-y", "-nostdin", "-loglevel", "error",
                "-i", tmp_in,
                "-c", "copy",
                "-movflags", "+faststart",
                tmp_out,
            ],
            capture_output=True,
            timeout=1800,
        )
        if proc.returncode != 0:
            err = proc.stderr.decode("utf-8", errors="replace")[:500]
            # Nicht-fatal: Original behalten (Backend-Fallback deckt es ab).
            log.warning("faststart remux fehlgeschlagen (%s): %s", original_name, err)
            return raw, ext, None
        out = Path(tmp_out).read_bytes()
        if not out:
            log.warning("faststart remux leer (%s) — Original behalten", original_name)
            return raw, ext, None
        # Verifikation: moov muss jetzt vorne liegen; sonst Original behalten.
        if _moov_at_end(out):
            log.warning("faststart remux Ergebnis hat moov weiterhin hinten (%s)", original_name)
            return raw, ext, None
        log.info("faststart: %s %d → %d bytes", original_name, len(raw), len(out))
        note = "(moov-Atom nach vorne geschrieben)"
        return out, ext, note
    except (subprocess.TimeoutExpired, OSError) as exc:
        log.warning("faststart remux abgebrochen (%s): %s", original_name, exc)
        return raw, ext, None
    finally:
        for p in (tmp_in, tmp_out):
            if p:
                try:
                    os.unlink(p)
                except OSError:
                    pass


def prepare_storage(raw: bytes, original_name: str) -> Tuple[bytes, str, Optional[str]]:
    """Entscheide, ob das Original gespeichert oder konvertiert wird.

    Returns (audio_bytes, final_extension, conversion_note). Für native
    Formate: unverändert zurück, kein Hinweis. Sonst: MP3 128k mono via
    ffmpeg (Fehler → RuntimeError-Meldung).

    Change 011 (2026-08-17): M4A/MP4 mit moov-Atom am Dateiende werden
    beim Speichern via ``-c copy -movflags +faststart`` remuxt — das
    behebt den „empty audio"-Bug an der WURZEL (die Datei ist danach
    überall lesbar), statt dass das ASR-Backend bei jeder Transkription
    eine Temp-Kopie baut. Fehler beim Remux sind nicht-fatal: das
    Original bleibt, der Backend-Fallback deckt den Rest ab.
    """
    ext = Path(original_name).suffix.lower()
    if is_native_audio(original_name):
        if ext in (".m4a", ".m4b", ".mp4") and _moov_at_end(raw):
            return _faststart_remux(raw, original_name)
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


def _wav_has_audio(out: bytes) -> bool:
    """Echtes WAV mit Audio-Frames? (nicht nur Header)

    Live-Befund 2026-08-17: M4A mit trailing moov (moov-Atom am Dateiende,
    ~98,8 %) dekodiert über die nicht-seekbare stdin-Pipe nur den WAV-Header
    (78 Bytes) — returncode 0 trotzdem. `if not out` fängt das nicht
    (78 Bytes ≠ leer). Zusätzliche Falle: ffmpeg schreibt bei Pipe-Ausgabe
    für unbekannte Größen die Platzhalter `0xFFFFFFFF` (RIFF- UND
    data-Chunk) — size > 0 allein reicht also nicht, der data-Chunk muss
    zur Gesamtlänge passen.
    """
    if len(out) < 44 or out[:4] != b"RIFF" or out[8:12] != b"WAVE":
        return False
    # data-Chunk suchen (PCM: WAV hat genau einen) — dessen Größe muss
    # plausibel sein: > 0, nicht 0xFFFFFFFF (ffmpeg-Platzhalter) und in die
    # Gesamtlänge passend (sonst Header-only / abgeschnitten).
    idx = out.find(b"data", 12)
    if idx < 0 or idx + 8 > len(out):
        return False
    size = int.from_bytes(out[idx + 4 : idx + 8], "little")
    if size == 0:
        return False
    if size == 0xFFFFFFFF:
        # ffmpeg-Pipe-Platzhalter „unbekannt bis EOF": gültig, wenn nach dem
        # data-Header tatsächlich Frames folgen (echte Datei) — die kaputte
        # Header-only-Variante (78 B) endet EXAKT am data-Header (0 Bytes).
        return len(out) - (idx + 8) >= 44  # mind. ein paar Frames
    return idx + 8 + size <= len(out)


def convert_to_wav_16k_mono(raw: bytes, original_name: str) -> Tuple[bytes, str, Optional[str]]:
    """Immer-Konvertierung nach 16 kHz 16 bit mono WAV via ffmpeg.

    Wird für (a) exotische Upload-Formate und (b) Backends ohne
    Compressed-Support (on-the-fly beim Transkribieren) genutzt.

    Fix 2026-08-17 (M4A trailing moov): Erst Pipe-Versuch (schnell, kein
    Temp-File) — bei leerer ODER Header-only-Ausgabe (returncode 0, aber
    kein data-Chunk!) Fallback auf SEEKBARE Temp-Datei. Container-Formate
    mit moov am Ende (MP4/M4A/3GP von Smartphones) sind über eine
    nicht-seekbare Pipe nicht dekodierbar (ffmpeg muss zum Dateiende
    springen); dieselbe Datei als Datei-Input dekodiert einwandfrei.
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
        if proc.returncode == 0 and _wav_has_audio(proc.stdout):
            out = proc.stdout
            log.info("Converted %s: %d → %d bytes", original_name, len(raw), len(out))
            note = f"(konvertiert von {ext or 'unbekannt'} nach WAV)"
            return out, ".wav", note
        # Pipe scheiterte (0 Bytes oder Header-only) → seekbare Temp-Datei.
        # Die richtige Endung ist wichtig: ffmpeg erkennt das Format am
        # Suffix, eine generische .tmp würde als "data" fehlinterpretiert.
        err_hint = proc.stderr.decode("utf-8", errors="replace")[:200].strip()
        with tempfile.NamedTemporaryFile(suffix=ext or ".m4a", delete=False) as tf:
            tf.write(raw)
            tmp_name = tf.name
        try:
            p2 = subprocess.run(
                [
                    "ffmpeg", "-y", "-nostdin", "-loglevel", "error",
                    "-i", tmp_name,
                    "-ar", "16000", "-ac", "1", "-sample_fmt", "s16",
                    "-f", "wav",
                    "pipe:1",
                ],
                capture_output=True,
                timeout=300,
            )
            if p2.returncode != 0 or not _wav_has_audio(p2.stdout):
                err = p2.stderr.decode("utf-8", errors="replace")[:500] or err_hint or "leere Ausgabe"
                raise RuntimeError(f"Konnte {original_name} nicht konvertieren: {err}")
            out = p2.stdout
            log.info(
                "Converted %s (Temp-Datei-Fallback, trailing moov): %d → %d bytes",
                original_name, len(raw), len(out),
            )
            note = f"(konvertiert von {ext or 'unbekannt'} nach WAV)"
            return out, ".wav", note
        finally:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
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
