"""Original-Audio herunterladen: Dateiname und Typ müssen stimmen (19.09.2026).

User-Report: „die original audio-datei im exportfenster herunterladen" ging
nicht. Ursache: Der Anzeigename einer konvertierten Aufnahme trägt eine Notiz
(``"name.webm (konvertiert von .webm nach MP3)"``) und wurde **wörtlich** als
Download-Dateiname geschickt — die Datei landete ohne brauchbare Endung auf dem
Gerät, während im MIME-Feld noch der alte Typ (``audio/wav``) stand, obwohl auf
der Platte eine MP3 lag.

Festschreibung:
* Der Download-Name hat die Endung der **abgelegten** Datei und keine Notiz.
* Der Content-Type folgt der Endung der abgelegten Datei, nicht dem DB-Feld.
"""
from __future__ import annotations

from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Reine Funktionen (kein Server nötig)
# ---------------------------------------------------------------------------
def _rec(original_name: str, stored_path: str, mime: str = "audio/wav"):
    from app.routers import recordings as rec_mod

    class _R:
        pass

    r = _R()
    r.original_name = original_name
    r.stored_path = stored_path
    r.mime = mime
    return r, rec_mod


def test_download_name_ohne_konvertier_notiz_mit_richtiger_endung():
    r, mod = _rec(
        "recording_1789746763803.webm (konvertiert von .webm nach MP3)",
        "/data/audio/1/bb62057dbfb14fce898cf53f1b4beee2.mp3",
    )
    name = mod._download_name(r)
    assert name == "recording_1789746763803.mp3", name
    assert "konvertiert" not in name
    assert name.endswith(".mp3"), "ohne echte Endung ist die Datei am Handy unbrauchbar"


def test_download_name_laubt_punkte_und_leerzeichen_im_namen():
    r, mod = _rec("18. Sept. um 12-31.m4a", "/data/audio/1/576b0c3dae1b408d857a7b893f5ef375.m4a")
    assert mod._download_name(r) == "18. Sept. um 12-31.m4a"


def test_download_name_ohne_endung_faellt_auf_abgelegte_datei_zurueck():
    r, mod = _rec("Sprachnotiz", "/data/audio/1/abc.mp3")
    assert mod._download_name(r) == "Sprachnotiz.mp3"


def test_guess_mime_folgt_der_abgelegten_datei():
    _, mod = _rec("x", "/data/audio/1/abc.mp3", mime="audio/wav")
    assert mod._guess_mime("/data/audio/1/abc.mp3", "audio/wav") == "audio/mpeg", (
        "nach webm→mp3 bleibt das DB-Feld auf audio/wav — die Endung muss gewinnen"
    )


def test_guess_mime_bleibt_bei_unbekannter_endung_auf_dem_feld():
    _, mod = _rec("x", "/data/audio/1/abc.dat", mime="audio/webm")
    assert mod._guess_mime("/data/audio/1/abc.dat", "audio/webm") == "audio/webm"


# ---------------------------------------------------------------------------
# Voller Weg über den HTTP-Endpunkt
# ---------------------------------------------------------------------------
@pytest.fixture()
def client(tmp_path, monkeypatch):
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from sqlmodel import SQLModel, create_engine

    from app import db as db_module
    from app.config import settings
    from app.main import app

    eng = create_engine(f"sqlite:///{tmp_path / 'dlname.db'}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(eng)
    monkeypatch.setattr(db_module, "engine", eng)
    audio_dir = tmp_path / "audio"
    audio_dir.mkdir(exist_ok=True)
    monkeypatch.setattr(settings, "AUDIO_DIR", audio_dir)
    monkeypatch.setattr(settings, "OIDC_ENABLED", False)
    from fastapi.testclient import TestClient

    with TestClient(app) as c:
        yield c


def test_endpunkt_liefert_brauchbaren_namen_und_typ(client, tmp_path):
    """Der Download muss eine Datei mit richtiger Endung und richtigem Typ liefern."""
    from app.db import engine
    from app.models import Recording
    from sqlmodel import Session, select

    audio = tmp_path / "audio" / "konv.mp3"
    audio.write_bytes(b"ID3fake-mp3-bytes")

    resp = client.post("/api/recordings", files={"file": ("original.mp3", b"fake-audio-bytes", "audio/mpeg")})
    assert resp.status_code == 201, resp.text
    uid = resp.json()["uid"]

    with Session(engine) as s:
        rec = s.exec(select(Recording).where(Recording.uid == uid)).first()
        rec.status = "done"
        rec.stored_path = str(audio)
        rec.mime = "audio/wav"                      # veraltetes Feld, wie in Produktion
        rec.original_name = "original.webm (konvertiert von .webm nach MP3)"
        s.add(rec)
        s.commit()

    r = client.get(f"/api/recordings/{uid}/audio")
    assert r.status_code == 200, r.text
    disp = r.headers.get("content-disposition", "")
    assert "konvertiert" not in disp, f"Notiz im Dateinamen: {disp}"
    assert ".mp3" in disp, f"keine echte Endung: {disp}"
    assert r.headers.get("content-type", "").startswith("audio/mpeg"), r.headers.get("content-type")
