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
    b"ftyp",   # MP4 / M4A
    b"ID3",    # MP3 mit ID3-Tag
    b"\xff\xfb", b"\xff\xf3", b"\xff\xf2",  # MP3-Frame ohne ID3
    b"OggS",   # OGG / Opus
    b"FLAC",
    b"fLaC",
    b"#EXTM3U",  # M3U (theoretisch), eher nicht Audio — bewusst nicht hier
)


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
    if not any(head.startswith(m) for m in _AUDIO_MAGICS):
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
        ok, reason = is_valid_audio_file(Path(rec.stored_path))
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


def run_health_scan(session: Session, audio_dir: Path) -> int:
    """Kurzschluss: Scan + Markieren. Returns number of updated rows."""
    broken = scan_broken_recordings(session, audio_dir)
    if broken:
        names = ", ".join(b[0].uid[:8] for b in broken[:5])
        log.info("recording health: %d kaputt (%s%s)", len(broken), names,
                 "…" if len(broken) > 5 else "")
    return mark_broken(session, broken)
