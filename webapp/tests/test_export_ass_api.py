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

# ---------------------------------------------------------------------------
# Change 200 — Video-Export über den optionalen Render-Dienst
# ---------------------------------------------------------------------------
FORMAT_WEBM = {
    "id": "alpha_webm", "label": "WebM (nur Untertitel, transparent)",
    "ext": "webm", "mime": "video/webm", "alpha": True, "note": "transparent",
}


def _fake_service(monkeypatch, formats=None, **overrides):
    """Render-Dienst vortäuschen (die Webapp ruft ihn nie direkt im Test)."""
    from app.ass_export import render_client as rc

    rc.reset_cache()
    listing = list(formats or [])
    monkeypatch.setattr(rc, "formats", lambda: listing)
    monkeypatch.setattr(
        rc, "health",
        lambda ttl=None: {"status": "ok" if listing else "unavailable",
                          "formats": listing, "detail": "" if listing else "ConnectError"},
    )
    for name, fn in overrides.items():
        monkeypatch.setattr(rc, name, fn)
    return rc


def test_presets_melden_render_unavailable_ohne_dienst(client, monkeypatch):
    _fake_service(monkeypatch, formats=[])
    d = client.get("/api/export/presets").json()
    assert d["render_available"] is False
    assert d["render_formats"] == []
    assert "render_note" in d


def test_presets_melden_formate_wenn_dienst_laeuft(client, monkeypatch):
    _fake_service(monkeypatch, formats=[FORMAT_WEBM])
    d = client.get("/api/export/presets").json()
    assert d["render_available"] is True
    assert [f["id"] for f in d["render_formats"]] == ["alpha_webm"]


def test_render_startet_job_mit_ass_dauer_und_flaeche(client, monkeypatch):
    rid = _make_recording(client)
    calls = {}

    def fake_start(**kw):
        calls.update(kw)
        return {"id": "job123", "state": "queued", "progress": 0.0, "filename": "x.webm"}

    _fake_service(monkeypatch, formats=[FORMAT_WEBM], start=fake_start)
    r = client.post(f"/api/recordings/{rid}/export",
                    json={"mode": "render", "format": "alpha_webm", "preset": "highlight"})
    assert r.status_code == 202, r.text
    body = r.json()
    assert body["id"] == "job123"
    assert body["format_label"].startswith("WebM")
    # Das erzeugte ASS geht mit, die Fläche wird daraus gelesen (nicht geraten).
    assert b"[Script Info]" in calls["ass_bytes"]
    assert calls["width"] == 1920 and calls["height"] == 1080
    assert calls["duration_s"] >= 1.0
    assert calls["media"] is None          # WebM braucht keine Tonspur


def test_render_ohne_dienst_ist_503_mit_hinweis(client, monkeypatch):
    rid = _make_recording(client)
    _fake_service(monkeypatch, formats=[])
    r = client.post(f"/api/recordings/{rid}/export", json={"mode": "render"})
    assert r.status_code == 503
    assert r.json()["detail"]["error"] == "render_unavailable"
    assert "ass" in r.json()["detail"]["hint"].lower()


def test_render_unbekanntes_format_ist_400(client, monkeypatch):
    rid = _make_recording(client)
    _fake_service(monkeypatch, formats=[FORMAT_WEBM])
    r = client.post(f"/api/recordings/{rid}/export",
                    json={"mode": "render", "format": "alpha_mov"})
    assert r.status_code == 400
    assert r.json()["detail"]["error"] == "unsupported_format"
    assert "alpha_mov" in r.json()["detail"]["detail"]


def test_render_status_wird_durchgereicht(client, monkeypatch):
    rid = _make_recording(client)
    _fake_service(monkeypatch, formats=[FORMAT_WEBM],
                  status=lambda jid: {"id": jid, "state": "running", "progress": 0.42})
    r = client.get(f"/api/recordings/{rid}/export/jobs/job123")
    assert r.status_code == 200
    assert r.json()["progress"] == 0.42


def test_render_datei_wird_gestreamt_mit_dateinamen(client, monkeypatch):
    import httpx as _httpx

    rid = _make_recording(client)
    upstream = _httpx.Response(200, headers={
        "content-type": "video/webm",
        "content-disposition": 'attachment; filename="folge.webm"',
    }, content=b"webm-daten")

    class FakeClient:
        def close(self):
            pass

    _fake_service(monkeypatch, formats=[FORMAT_WEBM],
                  open_file=lambda jid: (FakeClient(), upstream))
    r = client.get(f"/api/recordings/{rid}/export/jobs/job123/file")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("video/webm")
    assert "folge.webm" in r.headers["content-disposition"]
    assert r.content == b"webm-daten"


def test_render_job_fehler_werden_zu_klaren_status(client, monkeypatch):
    from app.ass_export import render_client as rc

    rid = _make_recording(client)

    def expired(jid):
        raise rc.RenderError("expired", "Die Datei wurde bereits aufgeräumt (24 h).")

    _fake_service(monkeypatch, formats=[FORMAT_WEBM], status=expired)
    r = client.get(f"/api/recordings/{rid}/export/jobs/job123")
    assert r.status_code == 410
    assert r.json()["detail"]["error"] == "expired"


# ---------------------------------------------------------------------------
# Regression: der Video-Download brach mit 500 ab (live 18.09.)
# ---------------------------------------------------------------------------
def test_open_file_liest_die_fehlermeldung_auch_bei_streaming(monkeypatch):
    """httpx wirft bei ungarer Streaming-Antwort ResponseNotRead -> 500 statt 404."""
    import httpx as _httpx

    from app.ass_export import render_client as rc

    body = b'{"detail":{"error":"unknown_job","detail":"Auftrag unbekannt"}}'
    streamed = _httpx.Response(404, stream=_httpx.ByteStream(body),
                              headers={"content-type": "application/json"})

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        def build_request(self, *a, **k):
            return _httpx.Request("GET", "http://render/jobs/x/file")

        def send(self, request, stream=False):
            return streamed

        def close(self):
            pass

    monkeypatch.setattr(rc.httpx, "Client", FakeClient)
    with pytest.raises(rc.RenderError) as exc:
        rc.open_file("job1")
    assert exc.value.code == "unknown_job"
    assert "unbekannt" in exc.value.detail


def test_unbekannter_auftrag_beim_download_ist_404_nicht_500(client, monkeypatch):
    """Endpunkt-Sicht: klare Antwort, kein interner Fehler."""
    from app.ass_export import render_client as rc

    rid = _make_recording(client)

    def unknown(job_id):
        raise rc.RenderError("unknown_job", "Auftrag unbekannt (oder Dienst neu gestartet).")

    _fake_service(monkeypatch, formats=[FORMAT_WEBM], open_file=unknown)
    r = client.get(f"/api/recordings/{rid}/export/jobs/job123/file")
    assert r.status_code == 404, r.text
    assert r.json()["detail"]["error"] == "unknown_job"
