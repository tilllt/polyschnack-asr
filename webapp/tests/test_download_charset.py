"""Download-Export: charset=utf-8 im Content-Type (Fix 2026-08-15).

User-Report: Umlaute im TXT-Download als Sonderzeichen („Ã¤"-Artefakte).
Ursache: media_type ohne charset → Browser rät Windows-1252/Latin-1.
Der Endpoint muss für txt/srt/vtt explizit charset=utf-8 setzen.
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

    eng = create_engine(f"sqlite:///{tmp_path / 'dl.db'}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(eng)
    monkeypatch.setattr(db_module, "engine", eng)
    audio_dir = tmp_path / "audio"
    audio_dir.mkdir(exist_ok=True)
    monkeypatch.setattr(settings, "AUDIO_DIR", audio_dir)
    monkeypatch.setattr(settings, "OIDC_ENABLED", False)

    with TestClient(app) as c:
        yield c


def _make_done_recording(client, text: str) -> str:
    """Upload + direkt als done markieren (setzt die Anon-Session)."""
    resp = client.post(
        "/api/recordings",
        files={"file": ("umlaut-test.mp3", b"fake-audio-bytes", "audio/mpeg")},
    )
    assert resp.status_code == 201, resp.text
    rid = resp.json()["uid"]

    from app.db import engine
    from app.models import Recording
    from sqlmodel import Session, select

    with Session(engine) as s:
        rec = s.exec(select(Recording).where(Recording.uid == rid)).first()
        assert rec is not None
        rec.status = "done"
        rec.text = text
        s.add(rec)
        s.commit()
    return rid


def test_download_txt_has_charset_utf8(client):
    text = "Grüße aus Köln — Straße, Übung, Ärger, Süßwaren."
    rid = _make_done_recording(client, text)

    r = client.get(f"/api/recordings/{rid}/download?format=txt")
    assert r.status_code == 200, r.text
    ct = r.headers.get("content-type", "")
    assert "charset=utf-8" in ct.lower(), f"fehlt charset: {ct}"
    # Inhalt muss die Umlaute unverändert enthalten (UTF-8-dekodiert).
    assert "Grüße" in r.text
    assert "Köln" in r.text
    assert "Süßwaren" in r.text


def test_download_srt_vtt_also_utf8(client):
    text = "Grüße aus Köln."
    rid = _make_done_recording(client, text)

    for fmt in ("srt", "vtt"):
        r = client.get(f"/api/recordings/{rid}/download?format={fmt}")
        assert r.status_code == 200, r.text
        ct = r.headers.get("content-type", "")
        assert "charset=utf-8" in ct.lower(), f"{fmt} fehlt charset: {ct}"


def test_to_txt_normalises_line_ending():
    from app.service import to_txt

    assert to_txt("  Hallo\nWelt  ") == "Hallo\nWelt\n"
