"""Diagnose-Check für Modell-Status (Option B: Diarization via CrispASR).

Erwartung: /api/models/status liefert detaillierte Fehlerursachen statt nur
bool-Flags — unterscheidet diar-Service erreichbar (ok), HTTP-Fehler
(diar-error) und Verbindungsfehler (diar-unreachable).
"""
from unittest.mock import MagicMock, patch

import httpx
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

# ---------------------------------------------------------------------------
# _diarize_diagnosis: diar-Service-HTTP-Check
# ---------------------------------------------------------------------------


def test_diarize_diagnosis_ok():
    from app.routers import models as m

    resp = MagicMock(status_code=200)
    resp.raise_for_status.return_value = None
    resp.json.return_value = {"status": "ok"}
    with patch("httpx.get", return_value=resp) as mock_get:
        d = m._diarize_diagnosis()
    assert d["available"] is True
    assert d["code"] == "ok"
    assert mock_get.call_args[0][0].endswith("/health")


def test_diarize_diagnosis_http_error():
    from app.routers import models as m

    with patch("httpx.get") as mock_get:
        resp = httpx.Response(503, request=httpx.Request("GET", "http://diar:5096/health"))
        mock_get.return_value = resp
        d = m._diarize_diagnosis()
    assert d["available"] is False
    assert d["code"] == "diar-error"
    assert "HTTP" in d["message"]


def test_diarize_diagnosis_unreachable():
    from app.routers import models as m

    with patch("httpx.get", side_effect=Exception("connection refused")):
        d = m._diarize_diagnosis()
    assert d["available"] is False
    assert d["code"] == "diar-unreachable"
    assert "nicht erreichbar" in d["message"]


# ---------------------------------------------------------------------------
# _check_diarize: pyannote-Fallback für alte Images
# ---------------------------------------------------------------------------


def test_check_diarize_uses_service_when_no_pyannote():
    from app.routers import models as m

    with patch.object(m, "_pyannote_importable", return_value=False), \
         patch.object(m, "_diar_service_reachable", return_value=True):
        assert m._check_diarize() is True


def test_check_diarize_pyannote_fallback():
    from app.routers import models as m

    with patch.object(m, "_pyannote_importable", return_value=True):
        assert m._check_diarize() is True


# ---------------------------------------------------------------------------
# /api/models/status: neue Detail-Felder
# ---------------------------------------------------------------------------


def test_status_endpoint_has_diag_fields():
    from app.routers import models as m

    with patch.object(m, "_diarize_diagnosis", return_value={
            "available": True, "code": "ok", "service": "http://diar:5096",
            "message": "Diar-Service erreichbar (CrispASR).",
            "components": []}), \
         patch("app.routers.models.httpx.get") as mock_httpx:
        resp = MagicMock(status_code=200)
        resp.raise_for_status.return_value = None
        resp.json.return_value = {"device": "cuda"}
        mock_httpx.return_value = resp

        r = client.get("/api/models/status")
        assert r.status_code == 200
        body = r.json()
        assert "diarize_available" in body
        assert "diarize_diag" in body
        assert "diar_service" in body
        assert body["diarize_diag"]["code"] == "ok"


def test_status_endpoint_reports_unreachable():
    from app.routers import models as m

    with patch.object(m, "_diarize_diagnosis", return_value={
            "available": False, "code": "diar-unreachable",
            "service": "http://diar:5096",
            "message": "Diar-Service nicht erreichbar: conn refused",
            "components": []}), \
         patch("app.routers.models.httpx.get") as mock_httpx:
        resp = MagicMock(status_code=200)
        resp.raise_for_status.return_value = None
        resp.json.return_value = {"device": "cuda"}
        mock_httpx.return_value = resp

        r = client.get("/api/models/status")
        body = r.json()
        assert body["diarize_available"] is False
        assert body["diarize_diag"]["code"] == "diar-unreachable"


# ---------------------------------------------------------------------------
# /api/models/diarize/download: Kompatibilitäts-Stub (Option B)
# ---------------------------------------------------------------------------


def test_diarize_download_stub_ok():
    from app.routers import models as m

    with patch.object(m, "_check_diarize", return_value=True):
        r = client.post("/api/models/diarize/download")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "CrispASR" in body["message"]


def test_diarize_download_stub_unreachable():
    from app.routers import models as m

    with patch.object(m, "_check_diarize", return_value=False):
        r = client.post("/api/models/diarize/download")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "service-unreachable"
    assert "diar-models" in body["message"]
