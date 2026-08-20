"""Self-Healing (Change 014, 2026-08-18): DB-Eintrag OHNE gültige Datei.

Gegenrichtung zum Orphan-Sweep (`orphan_sweep.py`): Der Sweep räumt Dateien
OHNE DB-Eintrag ab — hier geht es um Recordings, deren `stored_path` fehlt
oder keine gültige Audio-Datei ist (z.B. 78-Byte-WAV, 0 Byte, falsche
Magic). Solche Einträge waren bisher weder abspiel- noch löschbar (Root
Cause: permissions.py vergibt für `user_id=None` nur "read" → DELETE 403).

Der Scan markiert kaputte Recordings als `status="failed"` mit klarem
Fehlertext (KEIN stilles Löschen — der User soll sehen, was passiert ist,
und selbst löschen können). Laufende Uploads werden über ein Alters-Fenster
geschützt (frisch geschriebene Datei vor dem DB-Commit), analog zum
Orphan-Sweep.
"""
from __future__ import annotations

import logging
import subprocess
import time
from pathlib import Path
from typing import List, Tuple

from sqlmodel import Session, select

from .models import Recording

log = logging.getLogger(__name__)

#: Dateien jünger als diese Schwelle werden NIE als kaputt markiert
#: (laufender Upload: Datei wird VOR dem DB-Commit geschrieben).
MIN_RECORDING_AGE_S = 3600  # 1 h

#: Mindestgröße für eine plausible Audio-Datei (WAV-Header allein = 44 B,
#: MP3-ID3-Tag könnte größer sein; alles darunter ist sicher kaputt).
MIN_AUDIO_SIZE = 256

#: Magic-Bytes, die eine Audio-Datei erkennbar machen (Audio-Container).
_AUDIO_MAGICS = (
    b"RIFF",   # WAV / AVI
    b"ID3",    # MP3 mit ID3-Tag
    b"\xff\xfb", b"\xff\xf3", b"\xff\xf2",  # MP3-Frame ohne ID3
    b"\xff\xf1", b"\xff\xf9",  # AAC-ADTS (mit/ohne CRC)
    b"OggS",   # OGG / Opus
    b"fLaC",   # FLAC
    b"\x1a\x45\xdf\xa3",  # WebM / EBML (MediaRecorder: Android/Chrome)
)

#: ISO-BMFF (MP4/M4A): Datei beginnt mit 4-Byte-Box-Größe, der Box-Typ
#: (z. B. "ftyp") steht an Position 4 — NICHT an Position 0. Change 034:
#: vorher wurde head.startswith(b"ftyp") geprüft → jede M4A-Datei
#: (iOS-Aufnahmen, Magic z. B. b"\x00\x00\x00\x1c") galt fälschlich als
#: "unbekanntes Format" und wurde als kaputt markiert (Fehlalarm).
_ISO_BMFF_TYPES = (b"ftyp", b"moov", b"mdat", b"free", b"wide", b"styp",
                   b"skip", b"pdin")


def _looks_like_audio(head: bytes) -> bool:
    """Erkennt Audio-Container an den ersten 8 Bytes (Header).

    WAV/MP3/OGG/FLAC/WebM starten direkt mit ihrer Magic; MP4/M4A mit
    4-Byte-Box-Größe + Box-Typ an Position 4.
    """
    if not head:
        return False
    if head.startswith(_AUDIO_MAGICS):
        return True
    return len(head) >= 8 and head[4:8] in _ISO_BMFF_TYPES


#: Konvertiertes Sidecar für Dateien mit unbekannter Magic, die ffmpeg aber
#: lesen kann (Change 034, User-Vorgabe): unbekannter Typ ≠ kaputt — erst
#: die ffmpeg-Konvertierung entscheidet. Konvention analog original_path()
#: (audio_utils): `<stored>.conv.mp3` im selben Ordner.
CONV_SUFFIX = ".conv.mp3"


def _conv_sidecar(stored: Path) -> Path:
    return stored.with_name(stored.name + CONV_SUFFIX)


def reconvert_to_sidecar(stored: Path) -> Tuple[bool, str]:
    """ffmpeg-Konvertierung (MP3 128k mono) → `<stored>.conv.mp3`.

    Gleiche Ziel-Konvention wie der Upload-Transcode in audio_utils.py
    (MP3 128 kbit/s mono — überall abspielbar, klein). Returns (ok, note);
    bei Misserfolg bleibt keine Temp-Datei zurück.
    """
    out = _conv_sidecar(stored)
    tmp = out.with_name(out.name + ".tmp")
    try:
        proc = subprocess.run(
            [
                "ffmpeg", "-y", "-nostdin", "-loglevel", "error",
                "-i", str(stored),
                "-vn", "-ac", "1", "-ar", "44100", "-b:a", "128k",
                "-f", "mp3", str(tmp),
            ],
            capture_output=True,
            timeout=1800,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        return False, f"ffmpeg nicht ausführbar: {exc}"
    if proc.returncode != 0:
        err = proc.stderr.decode("utf-8", errors="replace").strip()[:200]
        try:
            tmp.unlink()
        except OSError:
            pass
        return False, f"ffmpeg kann Datei nicht lesen ({err})"
    if not tmp.exists() or tmp.stat().st_size < MIN_AUDIO_SIZE:
        try:
            tmp.unlink()
        except OSError:
            pass
        return False, "ffmpeg-Konvertierung leer"
    tmp.replace(out)
    return True, ""


def _is_healthy(stored: Path) -> Tuple[bool, str]:
    """Gesundheit einer Datei (Scan- und Heil-Pfad).

    1. Magic-Check bestanden → heil.
    2. Unbekannte Magic → Konvertierungsversuch (ffmpeg → conv-Sidecar):
       erfolgreich (oder Sidecar existiert bereits) → heil, NICHT kaputt.
       3. ffmpeg scheitert → wirklich kaputt (mit ffmpeg-Fehlertext).
    Andere Gründe (fehlt / zu klein / leer / nicht lesbar) → kaputt.
    """
    ok, reason = is_valid_audio_file(stored)
    if ok:
        return True, ""
    if reason.startswith("unbekanntes Format"):
        conv = _conv_sidecar(stored)
        if conv.exists() and is_valid_audio_file(conv)[0]:
            return True, ""
        ok2, note = reconvert_to_sidecar(stored)
        if ok2:
            log.info("recording health: %s unbekannte Magic, aber ffmpeg "
                     "lesbar → Sidecar %s erzeugt", stored.name, conv.name)
            return True, ""
        return False, f"nicht lesbar ({note})"
    return False, reason


def is_valid_audio_file(path: Path) -> Tuple[bool, str]:
    """Prüft, ob *path* eine plausible Audio-Datei ist.

    Returns (ok, reason). Fehlend → (False, "fehlt"). Existierend aber
    zu klein / falsche Magic → (False, Grund). Ansonsten (True, "").
    """
    if not path.exists():
        return False, "Datei fehlt"
    try:
        size = path.stat().st_size
    except OSError:
        return False, "nicht lesbar"
    if size < MIN_AUDIO_SIZE:
        return False, f"zu klein ({size} Bytes)"
    try:
        with open(path, "rb") as fh:
            head = fh.read(8)
    except OSError:
        return False, "nicht lesbar"
    if not head:
        return False, "leer"
    if not _looks_like_audio(head):
        return False, f"unbekanntes Format (Magic: {head[:4]!r})"
    return True, ""


def scan_broken_recordings(
    session: Session,
    audio_dir: Path,
    min_age_s: int = MIN_RECORDING_AGE_S,
) -> List[Tuple[Recording, str]]:
    """Findet Recordings, deren Audio-Datei fehlt oder ungültig ist.

    Returns list of (recording, reason). Alte Einträge nur — jüngere als
    *min_age_s* werden übersprungen (laufender Upload).
    """
    now = time.time()
    broken: List[Tuple[Recording, str]] = []
    for rec in session.exec(select(Recording)).all():
        try:
            created = rec.created_at.timestamp()
        except (AttributeError, OSError, ValueError):
            created = 0.0
        if now - created < min_age_s:
            continue
        if rec.status == "processing" or rec.status == "queued":
            # Laufende Verarbeitung: Datei kann gerade neu geschrieben
            # werden (Re-Transcribe-Crop) — nicht anfassen.
            continue
        ok, reason = _is_healthy(Path(rec.stored_path))
        if not ok:
            broken.append((rec, reason))
    return broken


def mark_broken(session: Session, broken: List[Tuple[Recording, str]]) -> int:
    """Setzt kaputte Recordings auf status='failed' + klaren Fehlertext.

    Returns number of updated rows. Idempotent: bereits failed mit
    gleichem Fehler bleibt unverändert.
    """
    updated = 0
    for rec, reason in broken:
        msg = f"Audio-Datei fehlt oder ist beschädigt ({reason})"
        if rec.status != "failed" or rec.error != msg:
            rec.status = "failed"
            rec.error = msg
            updated += 1
    if updated:
        session.commit()
        log.info("recording health: %d kaputte Recording(s) als failed markiert", updated)
    return updated


def heal_false_failures(session: Session, audio_dir: Path) -> int:
    """Heilt Fehlalarme: failed wegen Health-Scan, Datei inzwischen gültig.

    Change 034: Der Magic-Check markierte MP4/M4A (und WebM) fälschlich als
    "unbekanntes Format" → viele gesunde Recordings wurden als failed
    markiert. Sobald die Datei laut aktuellem Check gültig ist, war die
    Markierung falsch → Status zurück auf "done" (mit Transkription) bzw.
    "uploaded" (ohne), error=None. Echte Schäden (Datei fehlt wirklich,
    zu klein, keine Audio-Magic) bleiben failed.

    Returns number of healed rows.
    """
    healed = 0
    prefix = "Audio-Datei fehlt oder ist beschädigt"
    for rec in session.exec(
        select(Recording).where(Recording.status == "failed")
    ).all():
        if not (rec.error or "").startswith(prefix):
            continue
        try:
            ok, _reason = _is_healthy(Path(rec.stored_path))
        except Exception:
            ok = False
        if not ok:
            continue
        rec.status = "done" if (rec.text or rec.segments) else "uploaded"
        rec.error = None
        healed += 1
    if healed:
        session.commit()
        log.info("recording health: %d Fehlalarm-Markierung(en) geheilt", healed)
    return healed


def run_health_scan(session: Session, audio_dir: Path) -> int:
    """Kurzschluss: Scan + Markieren. Returns number of updated rows."""
    broken = scan_broken_recordings(session, audio_dir)
    if broken:
        # uid kann bei Legacy-Datensätzen None sein → Fallback "?" (Change 028)
        names = ", ".join((b[0].uid or "?")[:8] for b in broken[:5])
        log.info("recording health: %d kaputt (%s%s)", len(broken), names,
                 "…" if len(broken) > 5 else "")
    marked = mark_broken(session, broken)
    heal_false_failures(session, audio_dir)
    return marked
