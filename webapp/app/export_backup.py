"""Backup-Roundtrip (Change 015): ZIP-Export + Import.

Ein Backup ist ein ZIP mit:
- ``transcript.json`` — kanonisches Backup-Schema v1 (Metadaten, Settings,
  Volltext, Segmente inkl. Word-Timings, Transkript-Versionen). KEINE
  DB-internen IDs — ``recording.uid`` ist eine frisch generierte Export-UUID.
- ``audio.<ext>`` — Kopie des Original-Audios (stored_path).
- ``transcript.txt`` + ``transcript.srt`` — Lese-Ausgabe (BOM wie Download).
- ``manifest.json`` — SHA-256 je Datei (Integrität, Import-Grundlage).

Datenschutz (anon): ``retention_minutes`` wird bei anonymen Recordings im
JSON vermerkt (null bei registrierten Usern); PromptTemplate/DeliveryTarget
werden als NAME exportiert (nicht als DB-FK), damit der Import auf einer
anderen Instanz nach Name auflösen kann.
"""
from __future__ import annotations

import hashlib
import io
import json
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from sqlmodel import select

from .config import settings
from .export import export_templates_dir, load_template, render_template
from .models import PromptTemplate, DeliveryTarget, Recording, TranscriptVersion, User

BACKUP_SCHEMA_VERSION = 1
BACKUP_TYPE = "polyschnack-backup"


# ---------------------------------------------------------------------------
# Serialisierung
# ---------------------------------------------------------------------------


def _iso(dt) -> Optional[str]:
    return dt.isoformat() if dt else None


def _export_settings(session, rec: Recording) -> Dict[str, Any]:
    """Recording-Toggles als JSON-freundliches Dict (FKs als Namen)."""
    prompt_name = None
    if rec.prompt_template_id:
        pt = session.get(PromptTemplate, rec.prompt_template_id)
        prompt_name = pt.name if pt else None
    delivery_name = None
    if rec.delivery_target_id:
        dtg = session.get(DeliveryTarget, rec.delivery_target_id)
        delivery_name = dtg.name if dtg else None
    return {
        "enable_vad": rec.enable_vad,
        "enable_diarize": rec.enable_diarize,
        "diarize_method": rec.diarize_method,
        "diarize_num_speakers": rec.diarize_num_speakers,
        "diarize_min_duration_off": rec.diarize_min_duration_off,
        "enable_streaming": rec.enable_streaming,
        "enable_noise_reduce": rec.enable_noise_reduce,
        "enable_enhance": rec.enable_enhance,
        "enable_punctuation": rec.enable_punctuation,
        "enable_llm_enhance": rec.enable_llm_enhance,
        "prompt_template_name": prompt_name,
        "delivery_target_name": delivery_name,
    }


def _retention_minutes_for(session, rec: Recording) -> Optional[int]:
    """Verbleibende Retention-Minuten bei anon-Recordings, sonst None."""
    if rec.user_id is None:
        return None
    u = session.get(User, rec.user_id)
    if u is None or u.kind != "anonymous":
        return None
    return settings.POLYSCHNACK_ANON_RETENTION_MINUTES


def build_transcript_json(
    session,
    rec: Recording,
    versions: List[TranscriptVersion],
    retention_minutes: Optional[int] = None,
) -> Dict[str, Any]:
    """Backup-Schema v1 als Dict (Kern von transcript.json)."""
    return {
        "schema_version": BACKUP_SCHEMA_VERSION,
        "type": BACKUP_TYPE,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "recording": {
            # Keine DB-Interna: frisch generierte Export-UUID.
            "uid": uuid.uuid4().hex,
            "title": rec.title,
            "original_name": rec.original_name,
            "language": rec.language,
            "backend": rec.backend,
            "duration_s": rec.duration_s,
            "created_at": _iso(rec.created_at),
            "segments_manual": rec.segments_manual,
            "settings": _export_settings(session, rec),
            "text": rec.text,
            "segments": rec.segments or [],
            "versions": [
                {
                    "version_no": v.version_no,
                    "kind": v.kind,
                    "text": v.text,
                    "segments": v.segments or [],
                    "backend": v.backend,
                    "language": v.language,
                    "created_at": _iso(v.created_at),
                }
                for v in versions
            ],
            "retention_minutes": retention_minutes,
        },
    }


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def build_backup_zip(
    session,
    rec: Recording,
    versions: List[TranscriptVersion],
    templates_dir=None,
) -> bytes:
    """Baut das komplette Backup-ZIP (Bytes) für *rec*.

    Reihenfolge im ZIP: transcript.json, audio.<ext>, transcript.txt,
    transcript.srt, manifest.json (zuletzt — Hash deckt alle anderen ab).
    """
    templates_dir = templates_dir or export_templates_dir()
    retention = _retention_minutes_for(session, rec)

    transcript = build_transcript_json(session, rec, versions, retention)
    transcript_bytes = json.dumps(
        transcript, ensure_ascii=False, indent=2
    ).encode("utf-8")

    audio_path = Path(rec.stored_path)
    audio_ext = audio_path.suffix or ".bin"
    audio_bytes = audio_path.read_bytes()

    # Lese-Ausgabe über die Standard-Templates (BOM wie Download).
    txt = render_template(
        load_template("txt", templates_dir),
        [],
        {"title": rec.title or Path(rec.original_name).stem,
         "media_file_name": Path(rec.original_name).stem,
         "media_file_name_with_ext": rec.original_name,
         "text": rec.text or ""},
    ).encode("utf-8-sig")
    srt = render_template(
        load_template("srt", templates_dir),
        rec.segments or [],
        {"title": rec.title or Path(rec.original_name).stem,
         "media_file_name": Path(rec.original_name).stem,
         "media_file_name_with_ext": rec.original_name,
         "text": rec.text or ""},
    ).encode("utf-8-sig")

    audio_name = f"audio{audio_ext}"
    files: Dict[str, bytes] = {
        "transcript.json": transcript_bytes,
        audio_name: audio_bytes,
        "transcript.txt": txt,
        "transcript.srt": srt,
    }
    manifest = {
        "schema_version": BACKUP_SCHEMA_VERSION,
        "files": {
            name: f"sha256:{_sha256(data)}" for name, data in files.items()
        },
    }
    files["manifest.json"] = json.dumps(
        manifest, ensure_ascii=False, indent=2
    ).encode("utf-8")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in files.items():
            zf.writestr(name, data)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Import (Phase 4)
# ---------------------------------------------------------------------------


class BackupError(Exception):
    """Validierungsfehler beim Import (→ 400 mit klarer Meldung)."""


def validate_backup_zip(zip_bytes: bytes) -> Tuple[Dict[str, Any], Dict[str, bytes]]:
    """Prüft manifest.json (SHA-256 je Datei) + schema_version.

    Liefert (transcript, contents) oder wirft BackupError.
    """
    try:
        zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
    except zipfile.BadZipFile as exc:
        raise BackupError("keine gültige ZIP-Datei") from exc

    names = set(zf.namelist())
    if "manifest.json" not in names:
        raise BackupError("manifest.json fehlt im Backup")
    try:
        manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise BackupError("manifest.json ist kein gültiges JSON") from exc

    if manifest.get("schema_version") != BACKUP_SCHEMA_VERSION:
        raise BackupError(
            f"nicht kompatible Backup-Version: {manifest.get('schema_version')} "
            f"(erwartet {BACKUP_SCHEMA_VERSION})"
        )
    files = manifest.get("files") or {}
    if not isinstance(files, dict):
        raise BackupError("manifest.json: files fehlt")

    contents: Dict[str, bytes] = {}
    for name, digest in files.items():
        if name not in names:
            raise BackupError(f"Datei {name} fehlt im ZIP (manifest-Mismatch)")
        data = zf.read(name)
        expected = str(digest)
        if expected.startswith("sha256:"):
            expected = expected[len("sha256:"):]
        if _sha256(data) != expected:
            raise BackupError(
                f"Integritätsprüfung fehlgeschlagen: {name} (SHA-256-Mismatch)"
            )
        contents[name] = data

    if "transcript.json" not in contents:
        raise BackupError("transcript.json fehlt im Backup")
    try:
        transcript = json.loads(contents["transcript.json"].decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise BackupError("transcript.json ist kein gültiges JSON") from exc
    if transcript.get("schema_version") != BACKUP_SCHEMA_VERSION:
        raise BackupError(
            f"nicht kompatible Backup-Version: {transcript.get('schema_version')}"
        )
    return transcript, contents


def import_backup_zip(
    session,
    zip_bytes: bytes,
    *,
    user_id: Optional[int],
    audio_dir: Path,
    anon: bool = False,
    original_name_fallback: str = "restored",
) -> Recording:
    """Stellt ein Backup-ZIP als neues Recording (status=done) wieder her.

    - Validierung (manifest-Hashes, schema_version) via validate_backup_zip.
    - Audio-Extension aus ``audio.*`` ableiten, nach storage_path_for
      kopieren (Change-014-Ordner), Dauer via probe_duration_path.
    - Duplikat-Erkennung über content_hash (blake2b wie Upload).
    - Einstellungen übernehmen (PromptTemplate/DeliveryTarget per NAME
      auflösen — fehlende Namen → None, kein Fehler).
    - TranscriptVersion-Snapshots in version_no-Reihenfolge anlegen.
    - Wirft BackupError bei Validierungsproblemen (→ 400 durch die Route).
    """
    from .audio_utils import probe_duration_path, storage_path_for
    from .crud import create_recording
    from .models import TranscriptVersion

    transcript, contents = validate_backup_zip(zip_bytes)
    rec_data = transcript.get("recording") or {}
    settings_data = rec_data.get("settings") or {}

    # Audio-Datei aus dem ZIP (Name: audio.<ext> — beliebige Endung).
    audio_name = next(
        (n for n in contents if n.startswith("audio.") and n != "audio"),
        None,
    )
    if audio_name is None:
        raise BackupError("Audio-Datei fehlt im Backup (audio.<ext>)")
    audio_bytes = contents[audio_name]
    ext = Path(audio_name).suffix or ".bin"
    if not ext.startswith("."):
        ext = f".{ext}"

    content_hash = hashlib.blake2b(audio_bytes, digest_size=16).hexdigest()

    stored = storage_path_for(user_id, ext, anon=anon)
    audio_dir.mkdir(parents=True, exist_ok=True)
    stored.write_bytes(audio_bytes)
    duration_s = probe_duration_path(stored) or rec_data.get("duration_s")

    # Settings-Namen auflösen (fehlen dürfen — Ziel-Instanz hat andere IDs).
    prompt_id = None
    if settings_data.get("prompt_template_name"):
        pt = session.exec(
            select(PromptTemplate).where(
                PromptTemplate.user_id == user_id,
                PromptTemplate.name == settings_data["prompt_template_name"],
            )
        ).first()
        prompt_id = pt.id if pt else None
    delivery_id = None
    if settings_data.get("delivery_target_name"):
        dtg = session.exec(
            select(DeliveryTarget).where(
                DeliveryTarget.user_id == user_id,
                DeliveryTarget.name == settings_data["delivery_target_name"],
            )
        ).first()
        delivery_id = dtg.id if dtg else None

    rec = create_recording(
        session,
        original_name=rec_data.get("original_name") or original_name_fallback,
        stored_path=str(stored),
        mime="audio/wav" if ext == ".wav" else "audio/mpeg",
        size_bytes=len(audio_bytes),
        duration_s=duration_s,
        enable_vad=bool(settings_data.get("enable_vad", False)),
        enable_diarize=bool(settings_data.get("enable_diarize", False)),
        diarize_num_speakers=settings_data.get("diarize_num_speakers"),
        diarize_min_duration_off=settings_data.get("diarize_min_duration_off"),
        diarize_method=settings_data.get("diarize_method"),
        enable_streaming=bool(settings_data.get("enable_streaming", False)),
        enable_noise_reduce=bool(settings_data.get("enable_noise_reduce", True)),
        enable_enhance=str(settings_data.get("enable_enhance") or "off"),
        content_hash=content_hash,
        user_id=user_id,
        owner_user_id=user_id,
    )
    # Titel (Change 014) direkt setzen — create_recording hat kein title-Feld.
    rec.title = rec_data.get("title")
    rec.status = "done"
    rec.text = rec_data.get("text")
    rec.segments = rec_data.get("segments")
    rec.segments_manual = bool(rec_data.get("segments_manual", False))
    rec.language = rec_data.get("language")
    rec.backend = rec_data.get("backend") or rec.backend
    rec.prompt_template_id = prompt_id
    rec.delivery_target_id = delivery_id
    if rec_data.get("created_at"):
        try:
            rec.created_at = datetime.fromisoformat(rec_data["created_at"])
        except ValueError:
            pass  # ungültiger Zeitstempel → Default (heute)
    session.add(rec)
    session.commit()
    session.refresh(rec)

    # Versions-Snapshots wiederherstellen (Diff/Restore nach Import).
    for v in rec_data.get("versions") or []:
        try:
            created = datetime.fromisoformat(v["created_at"]) if v.get("created_at") else None
        except ValueError:
            created = None
        session.add(TranscriptVersion(
            rec_id=rec.id,
            version_no=int(v.get("version_no", 0)),
            kind=str(v.get("kind") or "restore"),
            text=v.get("text"),
            segments=v.get("segments"),
            backend=str(v.get("backend") or ""),
            language=v.get("language"),
            created_at=created,
        ))
    session.commit()

    # Sidecar (Change 014): Titel + Dateiname neben der Datei spiegeln.
    try:
        from .audio_utils import write_sidecar

        write_sidecar(str(stored), rec.title, rec.original_name)
    except Exception:
        pass  # best-effort

    return rec
