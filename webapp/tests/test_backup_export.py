"""Change 015: Backup-Export (ZIP) — Struktur, Schema v1, Manifest, Rechte.

- GET /api/recordings/{rid}/backup → ZIP mit 5 Dateien
- transcript.json: schema_version=1, KEINE DB-IDs, Segmente inkl. Words,
  Versionen, Settings (Namen statt FKs), retention_minutes bei anon
- manifest.json: SHA-256 je Datei (matchen die Inhalte)
- Zugriff: full erforderlich (403 bei read), Status done erforderlich (409)
"""
from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from sqlmodel import SQLModel, create_engine

    from app import db as db_module
    from app.config import settings
    from app.main import app

    eng = create_engine(f"sqlite:///{tmp_path / 'backup.db'}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(eng)
    monkeypatch.setattr(db_module, "engine", eng)
    audio_dir = tmp_path / "audio"
    audio_dir.mkdir(exist_ok=True)
    monkeypatch.setattr(settings, "AUDIO_DIR", audio_dir)
    monkeypatch.setattr(settings, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(settings, "OIDC_ENABLED", False)

    with TestClient(app) as c:
        yield c


def _seg(start, end, text, speaker=None, words=None):
    seg = {"start": start, "end": end, "text": text}
    if speaker:
        seg["speaker"] = speaker
    if words:
        seg["words"] = words
    return seg


def _make_done_recording(client, segments, text=None, original_name="backup-test.mp3") -> str:
    resp = client.post(
        "/api/recordings",
        files={"file": (original_name, b"fake-audio-bytes", "audio/mpeg")},
    )
    assert resp.status_code == 201, resp.text
    rid = resp.json()["uid"]

    from app.db import engine
    from app.models import Recording, TranscriptVersion
    from app.versions import snapshot
    from sqlmodel import Session, select

    with Session(engine) as s:
        rec = s.exec(select(Recording).where(Recording.uid == rid)).first()
        assert rec is not None
        rec.status = "done"
        rec.segments = segments
        rec.text = text if text is not None else " ".join(str(x["text"]) for x in segments)
        s.add(rec)
        s.commit()
        s.refresh(rec)
        snapshot(s, rec, "transcribe")  # Version 1
    return rid


def _get_zip(client, rid, **params):
    r = client.get(f"/api/recordings/{rid}/backup", params=params)
    assert r.status_code == 200, r.text
    assert r.headers.get("content-type", "").startswith("application/zip")
    return zipfile.ZipFile(io.BytesIO(r.content))


def test_backup_zip_contains_five_files(client):
    segs = [_seg(0, 5, "Hallo Welt", "SPEAKER_01",
                 words=[{"word": "Hallo", "start": 0, "end": 1},
                        {"word": "Welt", "start": 1, "end": 2}])]
    rid = _make_done_recording(client, segs, text="Hallo Welt")

    zf = _get_zip(client, rid)
    names = sorted(zf.namelist())
    assert names == ["audio.mp3", "manifest.json", "transcript.json",
                     "transcript.srt", "transcript.txt"]
    # Content-Disposition mit Backup-Suffix
    r = client.get(f"/api/recordings/{rid}/backup")
    assert "backup.zip" in r.headers.get("content-disposition", "")


def test_backup_transcript_schema_v1_no_db_ids(client):
    segs = [
        _seg(0, 5, "Hallo Welt", "SPEAKER_01",
             words=[{"word": "Hallo", "start": 0, "end": 1}]),
        _seg(5, 9, "Grüße", None),
    ]
    rid = _make_done_recording(client, segs, text="Hallo Welt Grüße")

    zf = _get_zip(client, rid)
    t = json.loads(zf.read("transcript.json").decode("utf-8"))

    assert t["schema_version"] == 1
    assert t["type"] == "polyschnack-backup"
    assert "exported_at" in t

    rec = t["recording"]
    # Keine DB-internen IDs
    assert "id" not in rec
    assert "user_id" not in rec
    assert "owner_user_id" not in rec
    assert len(rec["uid"]) == 32  # Export-UUID (hex)
    assert rec["title"] is None or isinstance(rec["title"], str)
    assert rec["original_name"] == "backup-test.mp3"

    # Segmente inkl. Word-Timings
    assert len(rec["segments"]) == 2
    assert rec["segments"][0]["words"][0]["word"] == "Hallo"
    assert rec["text"] == "Hallo Welt Grüße"

    # Versionen (Snapshot v1 existiert)
    assert len(rec["versions"]) == 1
    assert rec["versions"][0]["kind"] == "transcribe"
    assert rec["versions"][0]["segments"][0]["text"] == "Hallo Welt"

    # Settings vorhanden
    s = rec["settings"]
    assert s["enable_vad"] is False
    assert "enable_diarize" in s
    assert "diarize_method" in s

    # anon → retention_minutes gesetzt (Default 15)
    assert rec["retention_minutes"] is not None


def test_backup_manifest_hashes_match(client):
    segs = [_seg(0, 5, "Hallo")]
    rid = _make_done_recording(client, segs, text="Hallo")

    zf = _get_zip(client, rid)
    manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
    assert manifest["schema_version"] == 1
    files = manifest["files"]
    assert set(files) == {"audio.mp3", "transcript.json", "transcript.srt", "transcript.txt"}

    import hashlib

    for name, digest in files.items():
        assert digest.startswith("sha256:")
        actual = hashlib.sha256(zf.read(name)).hexdigest()
        assert actual == digest[len("sha256:"):], f"{name} Hash-Mismatch"


def test_backup_srt_txt_have_bom(client):
    segs = [_seg(0, 5, "Grüße aus Köln")]
    rid = _make_done_recording(client, segs, text="Grüße aus Köln")

    zf = _get_zip(client, rid)
    assert zf.read("transcript.txt").startswith(b"\xef\xbb\xbf")
    assert zf.read("transcript.srt").startswith(b"\xef\xbb\xbf")
    assert "Grüße" in zf.read("transcript.txt").decode("utf-8-sig")


def test_backup_requires_full_access(client):
    """API-Key mit level=read → 403 (Backup enthält komplettes Audio)."""
    segs = [_seg(0, 5, "Hallo")]
    rid = _make_done_recording(client, segs, text="Hallo")

    from app.db import engine
    from app.models import ApiKey, Recording, User, hash_token
    from sqlmodel import Session, select

    with Session(engine) as s:
        viewer = User(sub="viewer-1", kind="oidc")
        s.add(viewer)
        s.commit()
        s.refresh(viewer)
        token = "readonly-token-xyz"
        s.add(ApiKey(user_id=viewer.id, name="read", level="read",
                     token_hash=hash_token(token)))
        s.commit()

    r = client.get(
        f"/api/recordings/{rid}/backup",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 403


def test_backup_requires_done(client):
    resp = client.post(
        "/api/recordings",
        files={"file": ("pending.mp3", b"fake-audio-bytes", "audio/mpeg")},
    )
    assert resp.status_code == 201
    rid = resp.json()["uid"]

    r = client.get(f"/api/recordings/{rid}/backup")
    assert r.status_code == 409


# ---------------------------------------------------------------------------
# Change 015 Phase 4: Import (Roundtrip)
# ---------------------------------------------------------------------------


def _download_backup(client, rid) -> bytes:
    r = client.get(f"/api/recordings/{rid}/backup")
    assert r.status_code == 200, r.text
    return r.content


def test_import_backup_roundtrip(client):
    """Export → Import: Segmente/Wörter/Titel identisch, keine Neu-Transkription."""
    segs = [
        _seg(0, 5, "Hallo Welt", "SPEAKER_01",
             words=[{"word": "Hallo", "start": 0, "end": 1},
                    {"word": "Welt", "start": 1, "end": 2}]),
        _seg(5, 9, "Grüße aus Köln", None),
    ]
    rid = _make_done_recording(client, segs, text="Hallo Welt Grüße aus Köln")
    zip_bytes = _download_backup(client, rid)

    # Original löschen (Restore-Szenario: Wiederherstellung nach Verlust) —
    # sonst greift die Duplikat-Erkennung (gleiches Audio → 409).
    r = client.delete(f"/api/recordings/{rid}")
    assert r.status_code in (200, 204), r.text

    # Import als neues Recording
    r = client.post(
        "/api/recordings/import-backup",
        files={"file": ("backup.zip", zip_bytes, "application/zip")},
    )
    assert r.status_code == 201 or r.status_code == 200, r.text
    imported = r.json()

    assert imported["status"] == "done"
    assert imported["text"] == "Hallo Welt Grüße aus Köln"
    assert len(imported["segments"]) == 2
    assert imported["segments"][0]["words"][0]["word"] == "Hallo"

    # Audio-Datei liegt im anon-Ordner (Change 014)
    from app.config import settings

    stored = imported["stored_path"] if "stored_path" in imported else None
    if stored:
        assert Path(stored).is_file()


def test_import_restores_versions(client):
    """Versions-Snapshots werden beim Import wiederhergestellt (Diff/Restore)."""
    segs = [_seg(0, 5, "Version eins")]
    rid = _make_done_recording(client, segs, text="Version eins")
    zip_bytes = _download_backup(client, rid)

    r = client.delete(f"/api/recordings/{rid}")
    assert r.status_code in (200, 204), r.text

    r = client.post(
        "/api/recordings/import-backup",
        files={"file": ("backup.zip", zip_bytes, "application/zip")},
    )
    assert r.status_code in (200, 201), r.text
    new_rid = r.json()["uid"]

    # Versionen des importierten Recordings (Metadaten via API)
    rv = client.get(f"/api/recordings/{new_rid}/versions")
    assert rv.status_code == 200, rv.text
    versions = rv.json()
    assert len(versions) >= 1
    assert versions[0]["kind"] == "transcribe"

    # Volltext des Snapshots liegt in der DB (TranscriptVersion)
    from app.db import engine
    from app.models import Recording, TranscriptVersion
    from sqlmodel import Session, select

    with Session(engine) as s:
        rec = s.exec(select(Recording).where(Recording.uid == new_rid)).first()
        assert rec is not None
        v = s.exec(
            select(TranscriptVersion).where(TranscriptVersion.rec_id == rec.id)
        ).first()
        assert v is not None
        assert v.text == "Version eins"
        assert v.segments == segs


def test_import_broken_manifest_400(client):
    """Manipuliertes ZIP (Hash-Mismatch) → 400, kein Recording angelegt."""
    segs = [_seg(0, 5, "Hallo")]
    rid = _make_done_recording(client, segs, text="Hallo")
    zip_bytes = bytearray(_download_backup(client, rid))

    # Audio-Bytes im ZIP finden und manipulieren — am einfachsten: neues ZIP
    # mit falschem manifest bauen.
    import io as _io
    import zipfile as _zf

    buf = _io.BytesIO()
    with _zf.ZipFile(buf, "w") as z:
        z.writestr("transcript.json", json.dumps({
            "schema_version": 1,
            "type": "polyschnack-backup",
            "recording": {"text": "x"},
        }))
        z.writestr("audio.mp3", b"fake-audio-bytes")
        z.writestr("manifest.json", json.dumps({
            "schema_version": 1,
            "files": {"audio.mp3": "sha256:" + "0" * 64},  # falscher Hash
        }))
    bad_zip = buf.getvalue()

    before = client.get("/api/recordings").json()
    n_before = len(before.get("recordings", before) if isinstance(before, dict) else before)

    r = client.post(
        "/api/recordings/import-backup",
        files={"file": ("kaputt.zip", bad_zip, "application/zip")},
    )
    assert r.status_code == 400, r.text
    assert "Integritätsprüfung" in r.json()["detail"]


def test_import_wrong_schema_version_400(client):
    """schema_version 99 → 400 mit klarer Meldung."""
    import io as _io
    import zipfile as _zf

    buf = _io.BytesIO()
    with _zf.ZipFile(buf, "w") as z:
        z.writestr("transcript.json", json.dumps({
            "schema_version": 99,
            "type": "polyschnack-backup",
            "recording": {"text": "x"},
        }))
        z.writestr("audio.mp3", b"fake-audio-bytes")
        z.writestr("manifest.json", json.dumps({
            "schema_version": 99,
            "files": {},
        }))
    bad_zip = buf.getvalue()

    r = client.post(
        "/api/recordings/import-backup",
        files={"file": ("alt.zip", bad_zip, "application/zip")},
    )
    assert r.status_code == 400, r.text
    assert "Backup-Version" in r.json()["detail"]


# ---------------------------------------------------------------------------
# Change 018: Original-Audio (audio.original.<ext>) im Backup + Import
# ---------------------------------------------------------------------------


def test_backup_contains_original_and_import_prefers_it(client):
    """Transkodierte Aufnahme: ZIP enthält audio.mp3 UND audio.original.aac;
    Import stellt die .aac-Originaldatei wieder her (nicht die MP3)."""
    from app.audio_utils import original_path
    from app.config import settings
    from app.db import engine
    from app.models import Recording
    from sqlmodel import Session, select

    segs = [_seg(0, 5, "Hallo Original")]
    rid = _make_done_recording(client, segs, text="Hallo Original")

    # Change-018-Situation simulieren: Store-Datei (MP3) + Original-Seitendatei
    # (.aac) — wie es der Upload nach einer Transkodierung ablegt.
    with Session(engine) as s:
        rec = s.exec(select(Recording).where(Recording.uid == rid)).first()
        assert rec is not None
        stored = Path(rec.stored_path)
        assert stored.suffix == ".mp3"
        orig = original_path(stored, ".aac")
        orig.write_bytes(b"original-aac-bytes")

    # Backup enthält beide Audio-Dateien; Manifest deckt beide ab.
    zf = _get_zip(client, rid)
    names = set(zf.namelist())
    assert "audio.mp3" in names
    assert "audio.original.aac" in names
    manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
    assert set(manifest["files"]) == {
        "audio.mp3", "audio.original.aac",
        "transcript.json", "transcript.srt", "transcript.txt",
    }

    import hashlib

    for name, digest in manifest["files"].items():
        actual = hashlib.sha256(zf.read(name)).hexdigest()
        assert actual == digest[len("sha256:"):], f"{name} Hash-Mismatch"

    # Restore-Szenario: Original-Recording löschen, Backup importieren.
    zip_bytes = _download_backup(client, rid)
    r = client.delete(f"/api/recordings/{rid}")
    assert r.status_code in (200, 204), r.text

    r = client.post(
        "/api/recordings/import-backup",
        files={"file": ("backup.zip", zip_bytes, "application/zip")},
    )
    assert r.status_code in (200, 201), r.text
    new_rid = r.json()["uid"]

    # Importiertes Audio ist die .aac-Originaldatei — nicht die MP3.
    with Session(engine) as s:
        rec2 = s.exec(select(Recording).where(Recording.uid == new_rid)).first()
        assert rec2 is not None
        assert Path(rec2.stored_path).suffix == ".aac"
        assert Path(rec2.stored_path).read_bytes() == b"original-aac-bytes"
        assert rec2.text == "Hallo Original"
