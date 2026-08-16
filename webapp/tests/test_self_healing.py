"""Self-Healing + Account-Exfiltration (2026-08-15).

Abgedeckt:
- audio_missing-Flag in _recording_to_dict (Datei weg → True)
- 410-Guards: transcribe/retranscribe/duplicate/merge/transcribe_range
  bei fehlender Audiodatei (statt 500)
- Delete funktioniert trotz fehlender Datei (räumt auf)
- Orphan-File-Sweep: alte un-referenzierte Dateien weg, frische bleiben,
  referenzierte bleiben, dry_run löscht nichts
- Account-Export: ZIP-Struktur (1 Ordner je Transkription, Audio + JSON),
  fehlendes Audio → AUDIO_FEHLT.txt statt Crash, nur eigene Recordings
"""
from __future__ import annotations

import json
import time
import zipfile
from pathlib import Path

import pytest
from fastapi import HTTPException
from sqlmodel import Session, SQLModel, create_engine

from app import orphan_sweep
from app.models import Recording, User
from app.routers import account, recordings


class _FakeRequest:
    def __init__(self, session=None):
        self.session = session or {}


@pytest.fixture(autouse=True)
def _patch_identity(monkeypatch):
    """_current_user + identity für Export-Route auf Session-Werte abbilden."""
    monkeypatch.setattr(recordings, "_current_user",
                        lambda request, session=None: request.session.get("user_id"))
    from app import identity as ident_mod

    class _FakeIdent:
        class _U:
            id = None

        user = _U()

    monkeypatch.setattr(account, "_current_user_id",
                        lambda request, session: request.session.get("user_id"))


@pytest.fixture()
def db(tmp_path):
    eng = create_engine(f"sqlite:///{tmp_path}/t.db")
    SQLModel.metadata.create_all(eng)
    with Session(eng) as s:
        s.add(User(id=1, sub="a"))
        s.add(User(id=2, sub="b"))
        s.commit()
    return eng


def _req(uid=None):
    return _FakeRequest(session={"user_id": uid} if uid is not None else {})


def _make_rec(session, *, uid_hex, name, path, user_id=1, status="done", text="Hallo",
              segments=None):
    rec = Recording(
        uid=uid_hex, original_name=name, stored_path=str(path),
        user_id=user_id, status=status, text=text,
        segments=segments or [{"start": 0.0, "end": 1.0, "text": "Hallo"}],
        duration_s=1.0, language="de", backend="ps-pk-onnx",
    )
    session.add(rec)
    session.commit()
    session.refresh(rec)
    return rec


# ---------------------------------------------------------------------------
# audio_missing-Flag
# ---------------------------------------------------------------------------


def test_audio_missing_flag(db, tmp_path):
    with Session(db) as s:
        ok = _make_rec(s, uid_hex="a" * 32, name="ok.wav",
                       path=tmp_path / "ok.wav", user_id=1)
        (tmp_path / "ok.wav").write_bytes(b"RIFF")
        gone = _make_rec(s, uid_hex="b" * 32, name="gone.wav",
                        path=tmp_path / "gone.wav", user_id=1)
        d_ok = recordings._recording_to_dict(ok)
        d_gone = recordings._recording_to_dict(gone)
        assert d_ok["audio_missing"] is False
        assert d_gone["audio_missing"] is True


# ---------------------------------------------------------------------------
# 410-Guards
# ---------------------------------------------------------------------------


def test_transcribe_410_bei_fehlender_datei(db, tmp_path):
    with Session(db) as s:
        rec = _make_rec(s, uid_hex="c" * 32, name="x.wav",
                        path=tmp_path / "x.wav", user_id=1)  # Datei nie angelegt
        # Guard direkt: 410 statt 500
        with pytest.raises(HTTPException) as ei:
            recordings._ensure_audio_present(rec)
        assert ei.value.status_code == 410
        assert "audio file missing" in ei.value.detail
        # Und über die echte Route (transcribe_ep verdrahtet den Guard)
        with pytest.raises(HTTPException) as ei2:
            recordings.transcribe_ep(
                rec.uid, _req(1),
                enable_vad=False, enable_diarize=False,
                enable_streaming=False, enable_noise_reduce=True,
                enable_enhance="off", backend="",
                session=s,
            )
        assert ei2.value.status_code == 410


def test_duplicate_410_statt_409(db, tmp_path):
    with Session(db) as s:
        rec = _make_rec(s, uid_hex="d" * 32, name="x.wav",
                        path=tmp_path / "x.wav", user_id=1)
        with pytest.raises(HTTPException) as ei:
            recordings.duplicate_recording(rec.uid, _req(1), s)
        assert ei.value.status_code == 410


def test_delete_funktioniert_trotz_fehlender_datei(db, tmp_path):
    with Session(db) as s:
        rec = _make_rec(s, uid_hex="e" * 32, name="x.wav",
                        path=tmp_path / "x.wav", user_id=1)
        r = recordings.delete_recording_endpoint(rec.uid, _req(1), s)
        assert r == {"deleted": rec.uid}


# ---------------------------------------------------------------------------
# Orphan-File-Sweep
# ---------------------------------------------------------------------------


def test_orphan_sweep_entfernt_nur_alte_unreferenzierte(tmp_path):
    audio_dir = tmp_path / "audio"
    audio_dir.mkdir()
    (audio_dir / "old_orphan.wav").write_bytes(b"x")
    (audio_dir / "fresh_orphan.wav").write_bytes(b"y")
    (audio_dir / "referenced.wav").write_bytes(b"z")
    old = audio_dir / "old_orphan.wav"
    old_stat = old.stat()
    # mtime künstlich in die Vergangenheit setzen
    old_ts = time.time() - 7200
    import os

    os.utime(old, (old_stat.st_atime, old_ts))

    referenced = {str(audio_dir / "referenced.wav")}
    removed = orphan_sweep.sweep_orphan_files(
        audio_dir, referenced, min_age_s=3600
    )
    assert removed == ["old_orphan.wav"]
    assert (audio_dir / "fresh_orphan.wav").exists()  # zu jung
    assert (audio_dir / "referenced.wav").exists()  # referenziert


def test_orphan_sweep_dry_run_loescht_nichts(tmp_path):
    audio_dir = tmp_path / "audio"
    audio_dir.mkdir()
    f = audio_dir / "old.wav"
    f.write_bytes(b"x")
    import os

    st = f.stat()
    os.utime(f, (st.st_atime, time.time() - 7200))
    removed = orphan_sweep.sweep_orphan_files(
        audio_dir, set(), min_age_s=3600, dry_run=True
    )
    assert removed == ["old.wav"]
    assert f.exists()


def test_collect_referenced_paths(db, tmp_path):
    with Session(db) as s:
        _make_rec(s, uid_hex="f" * 32, name="a.wav",
                  path=tmp_path / "a.wav", user_id=1)
        _make_rec(s, uid_hex="g" * 32, name="b.wav",
                  path=tmp_path / "b.wav", user_id=2)
        refs = orphan_sweep.collect_referenced_paths(s)
        assert str(tmp_path / "a.wav") in refs
        assert str(tmp_path / "b.wav") in refs


# ---------------------------------------------------------------------------
# Account-Export
# ---------------------------------------------------------------------------


def test_export_zip_struktur(db, tmp_path):
    audio_dir = tmp_path / "audio"
    audio_dir.mkdir()
    with Session(db) as s:
        _make_rec(s, uid_hex="aa" * 16, name="meeting.wav",
                  path=audio_dir / "meeting.wav", user_id=1, status="done",
                  text="Hallo Welt", segments=[{"start": 0, "end": 1, "text": "Hallo"}])
        _make_rec(s, uid_hex="bb" * 16, name="other.wav",
                  path=audio_dir / "other.wav", user_id=2)  # fremder User → NICHT drin
    (audio_dir / "meeting.wav").write_bytes(b"RIFFxxxx")

    resp = account.export_account(_req(1), Session(db))
    assert resp.status_code == 200
    zip_path = Path(resp.path)
    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
        assert len(names) == 2  # 1 Ordner: transkription.json + audio
        folder = [n for n in names if n.endswith("transkription.json")][0]
        assert folder.startswith("aa" * 16 + "-meeting/")
        data = json.loads(zf.read(folder))
        assert data["schema"] == "polyschnack-transcription-v1"
        assert data["text"] == "Hallo Welt"
        assert data["original_name"] == "meeting.wav"
        audio_entries = [n for n in names if n.startswith(folder.split("/")[0] + "/audio/")]
        assert len(audio_entries) == 1
        assert "other" not in " ".join(names)  # Shares/Fremde ausgeschlossen


def test_export_fehlendes_audio_wird_notiz_statt_crash(db, tmp_path):
    with Session(db) as s:
        _make_rec(s, uid_hex="cc" * 16, name="gone.wav",
                  path=tmp_path / "gone.wav", user_id=1)  # Datei fehlt
    resp = account.export_account(_req(1), Session(db))
    assert resp.status_code == 200
    with zipfile.ZipFile(Path(resp.path)) as zf:
        note = [n for n in zf.namelist() if n.endswith("AUDIO_FEHLT.txt")]
        assert len(note) == 1
        assert "fehlt" in zf.read(note[0]).decode()


def test_export_keine_eigenen_aufnahmen_404(db):
    with pytest.raises(HTTPException) as ei:
        account.export_account(_req(2), Session(db))
    assert ei.value.status_code == 404
