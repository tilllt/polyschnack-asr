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

Change 034 (2026-08-20, User-Vorgaben):
- Originaldateien können in Formaten vorliegen, mit denen der Rest von
  PolySchnack nichts anfangen kann (Browser-Player, ASR, Peaks, Export).
- Unbekannte Magic ≠ kaputt: Der Scan konvertiert die Datei per ffmpeg in
  eine verarbeitbare MP3 (128k mono — gleiche Konvention wie der
  Upload-Transcode) und biegt `stored_path` auf die Konvertierung um.
  Das Original bleibt erhalten (Archivierung) und liegt nach der
  Change-018-Konvention als `<stored>.orig<ext>` neben der Konvertierung —
  Exporte finden es per Glob weiterhin.
- Erst wenn ffmpeg die Datei nicht lesen kann, ist sie wirklich kaputt →
  `failed` mit ffmpeg-Fehlertext.
- Fälschlich als `failed` markierte Recordings (Datei inzwischen gültig)
  werden beim Scan zurückgesetzt (`done` bei Transkription, sonst
  `uploaded`).
"""
from __future__ import annotations

import logging
import subprocess
import time
from pathlib import Path
from typing import List, Tuple

from sqlmodel import Session, select

from .audio_utils import original_path
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


#: Magic-Präfixe, die der REST von PolySchnack direkt verarbeitet (Browser-
#: Player + ASR/Peaks): WAV, MP3, FLAC, MP4/M4A (ISO-BMFF). Ogg/WebM/AAC-
#: ADTS sind zwar Audio (erkennbar), aber NICHT überall abspielbar
#: (Safari/iOS: kein Ogg/WebM; ADTS: kein Browser) — die werden wie beim
#: Upload konvertiert (User-Vorgabe 20.08.: Konvertierung nur sparen, wenn
#: das Original direkt verarbeitbar ist).
_NATIVE_AUDIO_MAGICS = (
    b"RIFF",   # WAV
    b"ID3",    # MP3 mit ID3-Tag
    b"\xff\xfb", b"\xff\xf3", b"\xff\xf2",  # MP3-Frame ohne ID3
    b"fLaC",   # FLAC
)


def _is_directly_processable(stored: Path) -> bool:
    """True, wenn die Datei ohne Konvertierung von PolySchnack nutzbar ist."""
    try:
        with open(stored, "rb") as fh:
            head = fh.read(8)
    except OSError:
        return False
    if not head:
        return False
    if head.startswith(_NATIVE_AUDIO_MAGICS):
        return True
    return len(head) >= 8 and head[4:8] in _ISO_BMFF_TYPES


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


#: Zwischenname der ffmpeg-Konvertierung; wird nach Erfolg auf den
#: regulären `<uuid>.mp3`-Namen umgezogen (stored_path-Umbiegung).
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


def _repoint_to_converted(rec: Recording, stored: Path, conv: Path) -> Tuple[bool, str]:
    """stored_path auf die Konvertierung umbiegen, Original archivieren.

    Change-018-Konvention: `stored_path` zeigt auf die verarbeitbare Datei
    (`<uuid>.mp3`), das Original liegt als `<stored>.orig<ext>` daneben —
    damit funktionieren Player, ASR, Peaks und Exporte mit dem Rest von
    PolySchnack, und das Original bleibt für die Archivierung erhalten.
    """
    orig_suffix = stored.suffix or ".bin"
    new_stored = stored.with_suffix(".mp3")
    if new_stored == stored or new_stored.exists():
        new_stored = stored.with_name(stored.name + ".mp3")
    orig_target = original_path(new_stored, orig_suffix)
    try:
        if conv.exists():
            conv.replace(new_stored)
        else:
            return False, "Konvertierung fehlt"
        if stored.exists() and stored != new_stored:
            if orig_target.exists():
                # verlustfrei: Duplikat-Namen statt Überschreiben
                orig_target = orig_target.with_name(orig_target.name + ".dup")
            stored.rename(orig_target)
        rec.stored_path = str(new_stored)
        log.info("recording health: %s → %s (Original: %s)",
                 stored.name, new_stored.name, orig_target.name)
        return True, ""
    except OSError as exc:
        log.warning("recording health: Umbennung fehlgeschlagen (%s): %s",
                    stored.name, exc)
        return False, f"Konvertierung ok, aber Umbennung fehlgeschlagen ({exc})"


def _ensure_healthy(rec: Recording) -> Tuple[bool, str]:
    """Stellt sicher, dass der Rest von PolySchnack die Datei verarbeiten kann.

    1. Magic-Check bestanden UND direkt verarbeitbar (WAV/MP3/FLAC/MP4/M4A)
       → gesund, keine Konvertierung (User-Vorgabe 20.08.).
    2. Bekannt, aber nicht nativ verarbeitbar (Ogg/WebM/AAC-ADTS) oder
       unbekannte Magic → ffmpeg-Konvertierung: Erfolg → stored_path wird
       auf die MP3 umgebogen, Original als `.orig<ext>` archiviert
       (Change-018-Konvention). Fehlschlag → wirklich kaputt.
    Andere Gründe (fehlt / zu klein / leer / nicht lesbar) → kaputt.
    """
    stored = Path(rec.stored_path)
    ok, reason = is_valid_audio_file(stored)
    if not ok:
        if not reason.startswith("unbekanntes Format"):
            return False, reason
    elif _is_directly_processable(stored):
        return True, ""
    # Konvertierung nötig (unbekannte Magic oder nicht-natives Format)
    conv = _conv_sidecar(stored)
    if not (conv.exists() and is_valid_audio_file(conv)[0]):
        ok2, note = reconvert_to_sidecar(stored)
        if not ok2:
            return False, f"nicht lesbar ({note})"
    return _repoint_to_converted(rec, stored, conv)


def _ensure_preview(rec: Recording) -> None:
    """Sidecar-Preview für den Browser-Player sicherstellen (User-Vorgabe
    20.08.): Preview-Datei (`<stem>_preview.opus`, peaks-Konvention, Change 096)
    muss existieren und gültig sein — sonst wird sie (neu) erzeugt."""
    from .peaks import compute_preview_path

    stored = Path(rec.stored_path)
    preview = stored.with_name(stored.stem + "_preview.opus")
    if preview.exists() and preview.stat().st_size > 0 \
            and is_valid_audio_file(preview)[0]:
        return
    if preview.exists():
        try:
            preview.unlink()
        except OSError:
            pass
    compute_preview_path(stored)
    if preview.exists() and preview.stat().st_size > 0:
        log.info("recording health: Preview %s sichergestellt/regeneriert",
                 preview.name)


def scan_broken_recordings(
    session: Session,
    audio_dir: Path,
    min_age_s: int = MIN_RECORDING_AGE_S,
) -> List[Tuple[Recording, str]]:
    """Findet Recordings, deren Audio-Datei fehlt oder ungültig ist.

    Nebenbei (Change 034): unbekannte Formate werden konvertiert und
    `stored_path` umgebogen; fälschlich als failed markierte Recordings
    mit inzwischen gültiger Datei werden zurückgesetzt.

    Returns list of (recording, reason). Alte Einträge nur — jüngere als
    *min_age_s* werden übersprungen (laufender Upload).
    """
    now = time.time()
    broken: List[Tuple[Recording, str]] = []
    changed = False
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
        ok, reason = _ensure_healthy(rec)
        changed = True  # repoint/Heilung können stattgefunden haben
        if ok:
            _ensure_preview(rec)
            if (rec.status == "failed"
                    and (rec.error or "").startswith("Audio-Datei fehlt "
                                                     "oder ist beschädigt")):
                rec.status = "done" if (rec.text or rec.segments) else "uploaded"
                rec.error = None
                changed = True
                log.info("recording health: Fehlalarm-Markierung %s geheilt "
                         "→ %s", (rec.uid or "?")[:8], rec.status)
        else:
            broken.append((rec, reason))
            changed = True
    if changed:
        session.commit()
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


def _sweep_legacy_mp3_previews(session: Session, audio_dir: Path) -> int:
    """Altbestand der 64-kbps-MP3-Ära aufräumen (Change 098).

    Sobald die neue `.opus`-Preview (Change 096) existiert, wird die alte
    `<stem>_preview.mp3`-Sidecar gelöscht und ein evtl. veralteter
    `preview_path`-DB-Zeiger auf die `.opus`-Konvention umgestellt —
    sonst liefert der Preview-Endpoint nach dem Löschen 404.
    Dateien ohne `.opus`-Gegenstück bleiben liegen (der reguläre Scan
    stellt die neue Preview vorher sicher). Kein Recording referenziert
    die `.mp3`-Datei mehr (peaks.py erzeugt nur noch `.opus`).

    Returns number of removed legacy files.
    """
    removed = 0
    for mp3 in audio_dir.glob("**/*_preview.mp3"):
        opus = mp3.with_suffix(".opus")
        if not (opus.exists() and opus.stat().st_size > 0):
            continue
        try:
            mp3.unlink()
            removed += 1
        except OSError:
            continue
        for rec in session.exec(select(Recording).where(
                Recording.preview_path == str(mp3))).all():
            rec.preview_path = str(opus)
    if removed:
        session.commit()
        log.info("recording health: %d verwaiste MP3-Preview(s) entfernt, "
                 "DB-Zeiger auf Opus umgestellt", removed)
    return removed


def run_health_scan(session: Session, audio_dir: Path) -> int:
    """Kurzschluss: Scan + Markieren. Returns number of updated rows."""
    broken = scan_broken_recordings(session, audio_dir)
    if broken:
        # uid kann bei Legacy-Datensätzen None sein → Fallback "?" (Change 028)
        names = ", ".join((b[0].uid or "?")[:8] for b in broken[:5])
        log.info("recording health: %d kaputt (%s%s)", len(broken), names,
                 "…" if len(broken) > 5 else "")
    _sweep_legacy_mp3_previews(session, audio_dir)
    return mark_broken(session, broken)
