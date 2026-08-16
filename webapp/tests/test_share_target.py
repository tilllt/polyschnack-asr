"""Share-Target (Android PWA): POST /api/recordings?from=share antwortet mit
303-Redirect auf /r/{uid} statt JSON — der Android-Browser öffnet nach dem
„Teilen mit PolySchnack" die PWA direkt auf der neuen Aufnahme.

Der normale Upload (ohne from=share) bleibt unverändert JSON (201)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

UID_RE = re.compile(r"^/r/[0-9a-f]{32}$")


@pytest.fixture()
def client(tmp_path, monkeypatch):
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from sqlmodel import SQLModel, create_engine

    from app import db as db_module
    from app.config import settings
    from app.main import app

    eng = create_engine(f"sqlite:///{tmp_path / 'share.db'}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(eng)
    monkeypatch.setattr(db_module, "engine", eng)
    audio_dir = tmp_path / "audio"
    audio_dir.mkdir(exist_ok=True)
    monkeypatch.setattr(settings, "AUDIO_DIR", audio_dir)
    monkeypatch.setattr(settings, "OIDC_ENABLED", False)

    with TestClient(app) as c:
        yield c


def _share_upload(client, fname: str = "zoom.mp3") -> TestClient.response:
    return client.post(
        "/api/recordings?from=share",
        files={"file": (fname, b"fake-audio-bytes", "audio/mpeg")},
        data={"title": "Sprachnachricht", "text": "aus WhatsApp"},
        follow_redirects=False,
    )


def test_share_upload_redirectet_auf_aufnahme(client):
    resp = _share_upload(client)
    assert resp.status_code == 303, resp.text
    loc = resp.headers.get("location", "")
    assert UID_RE.match(loc), f"Location erwartet /r/<32-hex>, war: {loc}"


def test_share_duplikat_redirectet_auf_existierende_aufnahme(client):
    first = _share_upload(client)
    first_uid = first.headers["location"]
    second = _share_upload(client)
    assert second.status_code == 303, second.text
    assert second.headers["location"] == first_uid


def test_upload_ohne_from_bleibt_json_201(client):
    resp = client.post(
        "/api/recordings",
        files={"file": ("zoom.mp3", b"fake-audio-bytes", "audio/mpeg")},
    )
    assert resp.status_code == 201, resp.text
    assert resp.headers.get("content-type", "").startswith("application/json")
    body = resp.json()
    assert body.get("uid") and len(body["uid"]) == 32


def test_share_upload_legt_aufnahme_in_db_an(client):
    resp = _share_upload(client)
    uid = resp.headers["location"].rsplit("/", 1)[-1]
    detail = client.get(f"/api/recordings/{uid}")
    assert detail.status_code == 200, detail.text
    assert detail.json()["uid"] == uid
