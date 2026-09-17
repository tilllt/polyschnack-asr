"""Change 193 — API für den ASS-Caption-Export.

Geprüft werden die Zusagen der Spec:
* Preset-Katalog vollständig, mit Parameter-Schema.
* ASS-Download liefert eine Datei mit Kopf, Events und Dateinamen.
* Ohne Wortzeiten 409 ``no_word_timestamps`` (Hinweis: zuerst ausrichten).
* Unbekanntes Preset 404, ungültige Parameter 400, kaputtes JSON 400,
  unbekanntes Recording 404.
* Rendern ohne Render-Dienst 503 ``render_unavailable``.
* Hinweis-Header (Timing/Warnungen) erreichen den Client — kein stiller Export.
"""
from __future__ import annotations

import json
import uuid
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

    eng = create_engine(f"sqlite:///{tmp_path / 'ass.db'}",
                        connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(eng)
    monkeypatch.setattr(db_module, "engine", eng)
    audio_dir = tmp_path / "audio"
    audio_dir.mkdir(exist_ok=True)
    monkeypatch.setattr(settings, "AUDIO_DIR", audio_dir)
    monkeypatch.setattr(settings, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(settings, "OIDC_ENABLED", False)

    with TestClient(app) as c:
        yield c


def _make_recording(client, segments=None, status="done") -> str:
    """Upload + DB-Zustand setzen (Muster aus test_export_templates.py).

    Eindeutiger Dateiname pro Aufruf: gleicher Name + gleiche Bytes gelten im
    Upload als Duplikat und liefern keine ``uid`` zurück.
    """
    name = f"podcast-folge-{uuid.uuid4().hex[:8]}.mp3"
    resp = client.post(
        "/api/recordings",
        files={"file": (name, b"fake-audio-" + uuid.uuid4().bytes, "audio/mpeg")},
    )
    assert resp.status_code == 201, resp.text
    rid = resp.json()["uid"]
    if segments is None:
        segments = [{
            "start": 0.0, "end": 1.0, "text": "Hallo Welt",
            "words": [{"start": 0.0, "end": 0.4, "text": "Hallo"},
                      {"start": 0.5, "end": 0.9, "text": "Welt"}],
        }]
    from sqlmodel import Session, select

    from app.db import engine
    from app.models import Recording

    with Session(engine) as s:
        rec = s.exec(select(Recording).where(Recording.uid == rid)).first()
        assert rec is not None
        rec.status = status
        rec.segments = segments
        rec.text = " ".join(str(x.get("text") or "") for x in segments)
        s.add(rec)
        s.commit()
    return rid


# ---------------------------------------------------------------------------
# Preset-Katalog
# ---------------------------------------------------------------------------


def test_presets_endpoint_lists_all_standard_presets(client):
    r = client.get("/api/export/presets")
    assert r.status_code == 200, r.text
    data = r.json()
    names = [p["name"] for p in data["presets"]]
    assert names == ["classic", "highlight", "karaoke", "kinetic", "modern"]
    for preset in data["presets"]:
        assert preset["title"] and preset["description"]
        assert preset["parameters"]["words_per_line"] >= 1
        # Change 193 (GUI): nur benutzte Parameter — die UI baut daraus ihre Regler.
        assert preset["used_params"], f"{preset['name']}: used_params fehlt/leer"
        assert set(preset["used_params"]).issubset(preset["parameters"].keys())
    specs = data["parameter_specs"]
    assert specs["font_size"]["type"] == "int"
    assert specs["text_color"]["type"] == "color"
    assert specs["position"]["values"] == ["bottom", "center", "top"]
    # Solange kein Render-Container läuft, darf die UI keinen Render-Button zeigen.
    assert data["render_available"] is False


def test_preset_used_params_differ_per_preset(client):
    """Die UI darf keine Regler zeigen, die nichts bewirken."""
    data = client.get("/api/export/presets").json()
    by_name = {p["name"]: set(p["used_params"]) for p in data["presets"]}
    assert "accent_color" not in by_name["classic"]
    assert "accent_color" in by_name["highlight"]
    assert "pop_scale" in by_name["kinetic"] and "pop_scale" not in by_name["classic"]


# ---------------------------------------------------------------------------
# ASS-Download
# ---------------------------------------------------------------------------


def test_ass_download_returns_a_valid_document(client):
    rid = _make_recording(client)
    r = client.get(f"/api/recordings/{rid}/export/ass?preset=classic")
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("text/plain")
    assert 'filename="podcast-folge-' in r.headers["content-disposition"]
    assert '.ass"' in r.headers["content-disposition"]
    body = r.text
    assert body.startswith("[Script Info]")
    assert "[V4+ Styles]" in body and "[Events]" in body
    assert "Dialogue: 0,0:00:00.00," in body


def test_ass_download_reports_timing_and_counts_in_headers(client):
    rid = _make_recording(client)
    r = client.get(f"/api/recordings/{rid}/export/ass?preset=highlight")
    assert r.status_code == 200
    assert r.headers["x-polyschnack-timing"] == "real"
    assert r.headers["x-polyschnack-preset"] == "highlight"
    assert r.headers["x-polyschnack-words"] == "2"
    assert "x-polyschnack-lines" in r.headers
    assert r.headers["x-polyschnack-warnings"] == ""


def test_ass_download_applies_params_and_preset_defaults(client):
    rid = _make_recording(client)
    r = client.get(
        f"/api/recordings/{rid}/export/ass",
        params={"preset": "classic",
                "params": json.dumps({"font_size": 90, "text_color": "#123456"})},
    )
    assert r.status_code == 200, r.text
    style = [l for l in r.text.splitlines() if l.startswith("Style:")][0]
    assert ",90," in style
    assert "&H00563412" in style  # #123456 → BGR 563412


def test_ass_download_without_word_timings_is_409(client):
    rid = _make_recording(client, segments=[
        {"start": 0.0, "end": 2.0, "text": "nur segmentzeiten", "words": []},
    ])
    r = client.get(f"/api/recordings/{rid}/export/ass?preset=classic")
    assert r.status_code == 409, r.text
    assert r.json()["detail"]["error"] == "no_word_timestamps"
    assert "Re-align" in r.json()["detail"]["hint"]


def test_ass_download_of_pending_recording_is_409(client):
    rid = _make_recording(client, status="processing")
    r = client.get(f"/api/recordings/{rid}/export/ass?preset=classic")
    assert r.status_code == 409
    assert r.json()["detail"]["error"] == "not_transcribed"


def test_unknown_preset_is_404(client):
    rid = _make_recording(client)
    r = client.get(f"/api/recordings/{rid}/export/ass?preset=gibtsnicht")
    assert r.status_code == 404
    assert r.json()["detail"]["error"] == "unknown_preset"


def test_invalid_params_are_400(client):
    rid = _make_recording(client)
    r = client.get(
        f"/api/recordings/{rid}/export/ass",
        params={"preset": "classic", "params": json.dumps({"font_size": 9999})},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["error"] == "invalid_params"
    assert "font_size" in r.json()["detail"]["detail"]


def test_broken_params_json_is_400(client):
    rid = _make_recording(client)
    r = client.get(f"/api/recordings/{rid}/export/ass",
                   params={"preset": "classic", "params": "{nope"})
    assert r.status_code == 400
    assert r.json()["detail"]["error"] == "invalid_params"
    # Ein JSON-Array ist ebenfalls ungültig (Objekt erwartet).
    r2 = client.get(f"/api/recordings/{rid}/export/ass",
                    params={"preset": "classic", "params": "[1,2]"})
    assert r2.status_code == 400


def test_unknown_recording_is_404(client):
    r = client.get("/api/recordings/doesnotexist/export/ass?preset=classic")
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Render-Endpoint (Phase 4: noch kein Dienst)
# ---------------------------------------------------------------------------


def test_render_without_service_is_503_with_hint(client):
    rid = _make_recording(client)
    r = client.post(f"/api/recordings/{rid}/export",
                    json={"preset": "kinetic", "mode": "render"})
    assert r.status_code == 503
    detail = r.json()["detail"]
    assert detail["error"] == "render_unavailable"
    assert "ass" in detail["hint"].lower()


def test_render_validates_preset_and_timings(client):
    rid = _make_recording(client)
    assert client.post(f"/api/recordings/{rid}/export",
                       json={"preset": "nope"}).status_code == 404
    assert client.post(f"/api/recordings/{rid}/export",
                       json={"preset": "classic", "mode": "video"}).status_code == 400
    empty = _make_recording(client, segments=[
        {"start": 0.0, "end": 1.0, "text": "ohne worte", "words": []}])
    assert client.post(f"/api/recordings/{empty}/export",
                       json={"preset": "classic"}).status_code == 409
