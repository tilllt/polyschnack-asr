"""Change 014 (2026-08-18): Storage-Sicherheit + Self-Healing + Titel.

- User-Ordner: Uploads landen unter AUDIO_DIR/<user_id>/ bzw. anon/
- Health-Scan: DB-Eintrag ohne gültige Datei → status=failed
- Lösch-Rechte: Legacy-public (user_id=None) mit owner_user_id → löschbar
- Titel: PATCH /recordings/{rid}/title setzt DB + Sidecar
"""

from __future__ import annotations

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

    eng = create_engine(f"sqlite:///{tmp_path / 'c014.db'}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(eng)
    monkeypatch.setattr(db_module, "engine", eng)
    audio_dir = tmp_path / "audio"
    audio_dir.mkdir(exist_ok=True)
    monkeypatch.setattr(settings, "AUDIO_DIR", audio_dir)
    monkeypatch.setattr(settings, "OIDC_ENABLED", False)

    with TestClient(app) as c:
        yield c


def _upload(client, name: str = "zoom.mp3", data: bytes = b"fake-audio-bytes") -> dict:
    resp = client.post(
        "/api/recordings",
        files={"file": (name, data, "audio/mpeg")},
        data={"batch_id": "b1"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


# ---------------------------------------------------------------------------
# User-Ordner
# ---------------------------------------------------------------------------


def test_upload_legt_datei_in_anon_ordner(client):
    rec = _upload(client)
    from app.config import settings

    p = Path(rec["stored_path"] if "stored_path" in rec else "")
    # stored_path wird nicht serialisiert — prüfe über die DB
    from app.db import engine
    from app.models import Recording
    from sqlmodel import Session

    with Session(engine) as s:
        r = s.get(Recording, rec["id"])
        assert r is not None
        stored = Path(r.stored_path)
        assert stored.parent == settings.AUDIO_DIR / "anon", f"erwartet anon-Ordner, war {stored.parent}"
        assert stored.is_file()
        assert stored.suffix == ".mp3"


def test_upload_eingeloggter_user_legt_user_ordner_an(client):
    # OIDC aus → anon. Für den User-Ordner-Fall direkt die Helper-Funktion prüfen.
    from app.audio_utils import storage_path_for

    p = storage_path_for(42, ".wav")
    assert p.parent.name == "42"
    assert p.suffix == ".wav"
    assert p.parent.is_dir()  # Ordner wurde angelegt


# ---------------------------------------------------------------------------
# Health-Scan
# ---------------------------------------------------------------------------


def test_health_scan_markiert_fehlt_datei(client, tmp_path):
    rec = _upload(client)
    from app.db import engine
    from app.models import Recording
    from sqlmodel import Session

    # Datei entfernen + created_at in die Vergangenheit setzen (Alters-Schutz)
    with Session(engine) as s:
        r = s.get(Recording, rec["id"])
        assert r is not None
        Path(r.stored_path).unlink()
        import datetime as dt

        r.created_at = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=2)
        s.add(r)
        s.commit()

    from app.config import settings
    from app.recording_health import run_health_scan

    with Session(engine) as s:
        n = run_health_scan(s, settings.AUDIO_DIR)
        assert n == 1
        r = s.get(Recording, rec["id"])
        assert r.status == "failed"
        assert "Audio-Datei fehlt" in (r.error or "")


def test_health_scan_laesst_junge_uploads_in_ruhe(client):
    rec = _upload(client)
    from app.db import engine
    from app.models import Recording
    from app.recording_health import scan_broken_recordings
    from app.config import settings
    from sqlmodel import Session

    with Session(engine) as s:
        r = s.get(Recording, rec["id"])
        # Datei weg, aber created_at frisch → NICHT als kaputt markieren
        Path(r.stored_path).unlink()
        s.commit()
        broken = scan_broken_recordings(s, settings.AUDIO_DIR)
        assert broken == []


def test_health_scan_erkennt_78_byte_wav(client):
    """Das konkrete User-Symptom: 78-Byte-WAV (WAV-Header ohne Nutzdaten)."""
    rec = _upload(client, name="kaputt.wav", data=b"\x00" * 78)
    from app.db import engine
    from app.models import Recording
    from sqlmodel import Session
    import datetime as dt

    with Session(engine) as s:
        r = s.get(Recording, rec["id"])
        assert r is not None
        r.created_at = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=2)
        stored = Path(r.stored_path)
        s.add(r)
        s.commit()

    from app.config import settings
    from app.recording_health import is_valid_audio_file, run_health_scan

    # 78 Null-Bytes = keine Audio-Magic → ungültig
    ok, reason = is_valid_audio_file(stored)
    assert not ok
    with Session(engine) as s:
        n = run_health_scan(s, settings.AUDIO_DIR)
        assert n == 1
        r = s.get(Recording, rec["id"])
        assert r.status == "failed"


# ---------------------------------------------------------------------------
# Lösch-Rechte für Legacy-public
# ---------------------------------------------------------------------------


def test_legacy_public_mit_owner_loeschbar(client):
    """user_id=None + owner_user_id gesetzt → der Owner kann löschen (kein 403)."""
    from app.db import engine
    from app.models import Recording, User
    from sqlmodel import Session

    # anon-User anlegen (Owner)
    with Session(engine) as s:
        u = User(sub="legacy-owner-1", kind="anonymous", name="anon-1")
        s.add(u)
        s.commit()
        s.refresh(u)
        owner_id = u.id

    # Legacy-public-Recording: user_id=None, owner_user_id=owner_id
    from app.crud import create_recording

    with Session(engine) as s:
        rec = create_recording(
            s,
            original_name="legacy.mp3",
            stored_path="/nonexistent/legacy.mp3",
            mime="audio/mpeg",
            size_bytes=100,
            user_id=None,
            owner_user_id=owner_id,
        )
        rec_id = rec.id
        s.commit()

    # Als Owner löschen: Request mit anon-Session-Cookie ist komplex —
    # direkt permissions prüfen (der DELETE-Endpoint nutzt genau das).
    from app.permissions import get_access_level

    with Session(engine) as s:
        rec = s.get(Recording, rec_id)
        assert get_access_level(s, rec, owner_id, cap=None) == "full"
        # Fremder (anderer anon-User) bekommt nur read
        assert get_access_level(s, rec, 999999, cap=None) == "read"
        # Ohne owner_user_id: nur read für alle (außer Admin-Durchstich)
        rec.owner_user_id = None
        s.add(rec)
        s.commit()
        assert get_access_level(s, rec, owner_id, cap=None) == "read"


def test_herrenloses_legacy_admin_durchstich(client):
    from app.db import engine
    from app.models import Recording
    from app.permissions import ensure_access
    from fastapi import HTTPException
    from sqlmodel import Session

    from app.crud import create_recording

    with Session(engine) as s:
        rec = create_recording(
            s,
            original_name="herrenlos.mp3",
            stored_path="/nonexistent/herrenlos.mp3",
            mime="audio/mpeg",
            size_bytes=100,
            user_id=None,
            owner_user_id=None,
        )
        rec_id = rec.id
        s.commit()

    with Session(engine) as s:
        rec = s.get(Recording, rec_id)
        # Ohne Admin: 403
        with pytest.raises(HTTPException) as ei:
            ensure_access(s, rec, 1, "full")
        assert ei.value.status_code == 403
        # Mit Admin-Flag: ok
        ensure_access(s, rec, 1, "full", is_admin=True)


# ---------------------------------------------------------------------------
# Titel + Sidecar
# ---------------------------------------------------------------------------


def test_titel_patch_setzt_db_und_sidecar(client):
    rec = _upload(client)
    resp = client.patch(
        f"/api/recordings/{rec['uid']}/title",
        json={"title": "Besprechung KW34"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["title"] == "Besprechung KW34"
    assert body["original_name"] == "zoom.mp3"

    from app.db import engine
    from app.models import Recording
    from sqlmodel import Session

    with Session(engine) as s:
        r = s.get(Recording, rec["id"])
        assert r.title == "Besprechung KW34"
        # Sidecar liegt neben der Audio-Datei
        from app.audio_utils import sidecar_path, read_sidecar

        sc = read_sidecar(r.stored_path)
        assert sc is not None
        assert sc["title"] == "Besprechung KW34"
        assert sc["original_name"] == "zoom.mp3"
        assert sidecar_path(r.stored_path).is_file()


def test_titel_leer_400(client):
    rec = _upload(client)
    resp = client.patch(
        f"/api/recordings/{rec['uid']}/title",
        json={"title": "   "},
    )
    assert resp.status_code == 400


def test_serialisierung_liefert_title_fallback(client):
    rec = _upload(client)
    # Ohne gesetzten Titel: Fallback original_name
    assert rec["title"] == "zoom.mp3"
    assert rec["original_name"] == "zoom.mp3"


# ---------------------------------------------------------------------------
# Retention + User-Ordner (Datenschutz-Kette)
# ---------------------------------------------------------------------------


def test_anon_retention_loescht_datei_im_userordner(client):
    """Kern-Szenario (User-Frage 2026-08-18): Dateien anonymer User liegen
    jetzt in AUDIO_DIR/anon/ — der Retention-Sweep muss Row + Datei +
    Sidecar trotz User-Ordner komplett löschen."""
    rec = _upload(client)  # landet in AUDIO_DIR/anon/<uuid>.mp3
    from app.db import engine
    from app.models import Recording, User
    from sqlmodel import Session
    import datetime as dt

    with Session(engine) as s:
        r = s.get(Recording, rec["id"])
        assert r is not None
        stored = Path(r.stored_path)
        assert stored.parent.name == "anon", f"erwartet anon-Ordner, war {stored.parent}"
        assert stored.is_file()
        # Sidecar anlegen (wie nach Titel-Änderung)
        from app.audio_utils import write_sidecar

        write_sidecar(r.stored_path, "Mein Titel", r.original_name)
        assert Path(r.stored_path).with_suffix(".mp3.meta.json").is_file()

        # anon-User des Uploads finden + last_seen_at in die Vergangenheit setzen
        uid = r.user_id
        u = s.get(User, uid)
        assert u is not None and u.kind == "anonymous"
        u.last_seen_at = dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=999)
        s.add(u)
        s.commit()

    from app.retention import sweep

    with Session(engine) as s:
        n = sweep(s)
        assert n == 1, "anon-User wurde nicht vom Retention-Sweep erfasst"
        assert s.get(Recording, rec["id"]) is None, "Recording-Row blieb zurück!"
        assert s.get(User, uid) is None, "User-Row blieb zurück!"

    # Datei + Sidecar sind weg — trotz User-Ordner
    assert not stored.exists(), "Audio-Datei blieb im anon-Ordner zurück!"
    assert not stored.with_suffix(".mp3.meta.json").exists(), "Sidecar blieb zurück!"


def test_anon_retention_loescht_restore_recording_mit_owner_fallback(client):
    """Recovery-Restore legt user_id=None + owner_user_id=uid an — der
    Sweep muss auch diese (sonst herrenlosen) Recordings finden."""
    from app.db import engine
    from app.models import Recording, User
    from sqlmodel import Session
    import datetime as dt

    with Session(engine) as s:
        u = User(sub="anon-retention-2", kind="anonymous", name="anon-2",
                 last_seen_at=dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=999))
        s.add(u)
        s.commit()
        s.refresh(u)
        owner_id = u.id

        from app.crud import create_recording

        rec = create_recording(
            s,
            original_name="restore.mp3",
            stored_path="/tmp/restore-datei.mp3",
            mime="audio/mpeg",
            size_bytes=10,
            user_id=None,
            owner_user_id=owner_id,
        )
        rec_id = rec.id
        s.commit()

    from app.retention import sweep

    with Session(engine) as s:
        n = sweep(s)
        assert n == 1
        assert s.get(Recording, rec_id) is None, "Restore-Recording (owner_user_id) blieb zurück!"
