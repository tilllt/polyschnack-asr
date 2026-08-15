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
        resp = httpx.Response(503, request=httpx.Request("GET", "http://crispr-diar:5098/health"))
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
            "available": True, "code": "ok", "service": "http://crispr-diar:5098",
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
            "service": "http://crispr-diar:5098",
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
    # Option B: Modell liegt im diar-Container-Volume (./DATA/models/) —
    # kein Download-Stub mehr, daher die neue Meldung statt "diar-models".
    assert "Diar-Service nicht erreichbar" in body["message"]
    assert "./DATA/models" in body["message"]


# ---------------------------------------------------------------------------
# _aligner_diagnosis: Aligner-Service (crispr-align)
# ---------------------------------------------------------------------------


def test_aligner_diagnosis_ok():
    from app.routers import models as m

    resp = MagicMock(status_code=200)
    resp.raise_for_status.return_value = None
    resp.json.return_value = {"status": "ok", "service": "aligner",
                              "model": "qwen3-forced-aligner-0.6b-f16",
                              "max_duration_s": 400.0, "word_timestamps": True}
    with patch("httpx.get", return_value=resp) as mock_get, \
         patch("app.routers.models.os.getenv",
               return_value="http://crispr-align:5099"):
        d = m._aligner_diagnosis()
    assert d["available"] is True
    assert d["code"] == "ok"
    assert d["features"]["max_duration_s"] == 400.0
    assert d["features"]["word_timestamps"] is True
    assert mock_get.call_args[0][0].endswith("/health")


def test_aligner_diagnosis_unreachable():
    from app.routers import models as m

    with patch("httpx.get", side_effect=Exception("connection refused")), \
         patch("app.routers.models.os.getenv", return_value="http://crispr-align:5099"):
        d = m._aligner_diagnosis()
    assert d["available"] is False
    assert d["code"] == "aligner-unreachable"
    assert "nicht erreichbar" in d["message"]


def test_aligner_diagnosis_disabled():
    """POLYSCHNACK_ALIGN_WORDS=false → bewusst deaktiviert (kein Health-Call)."""
    from app.routers import models as m
    from app import aligner_client as ac

    # Der Import passiert IN der Funktion (from ..aligner_client import …),
    # deshalb das Quell-Modul patchen, nicht models.
    with patch.object(ac, "ALIGN_WORDS_ENABLED", False), \
         patch("httpx.get") as mock_get:
        d = m._aligner_diagnosis()
    assert d["available"] is False
    assert d["code"] == "aligner-disabled"
    mock_get.assert_not_called()


# ---------------------------------------------------------------------------
# /api/models/status: Aligner-Diagnose-Felder
# ---------------------------------------------------------------------------


def test_status_endpoint_has_aligner_fields():
    from app.routers import models as m

    with patch.object(m, "_diarize_diagnosis", return_value={
            "available": True, "code": "ok", "service": "http://crispr-diar:5098",
            "message": "ok", "features": {}, "components": []}), \
         patch.object(m, "_aligner_diagnosis", return_value={
            "available": True, "code": "ok", "service": "http://crispr-align:5099",
            "message": "ok", "features": {"word_timestamps": True},
            "components": []}), \
         patch("app.routers.models.httpx.get") as mock_httpx:
        resp = MagicMock(status_code=200)
        resp.raise_for_status.return_value = None
        resp.json.return_value = {"device": "cuda"}
        mock_httpx.return_value = resp

        r = client.get("/api/models/status")
        assert r.status_code == 200
        body = r.json()
        assert "align_available" in body
        assert "align_service" in body
        assert "aligner_diag" in body
        assert body["aligner_diag"]["code"] == "ok"
        assert body["features"]["word_timestamps"] is not None


# ---------------------------------------------------------------------------
# /api/models/services: Service-Matrix (Feature-Matrix-Basis)
# ---------------------------------------------------------------------------


def test_services_endpoint_matrix():
    from app.routers import models as m

    with patch.object(m, "_diarize_diagnosis", return_value={
            "available": True, "code": "ok", "service": "http://crispr-diar:5098",
            "message": "ok", "features": {"method": "pyannote"}, "components": []}), \
         patch.object(m, "_aligner_diagnosis", return_value={
            "available": True, "code": "ok", "service": "http://crispr-align:5099",
            "message": "ok", "features": {"word_timestamps": True,
                                          "max_duration_s": 400.0},
            "components": []}), \
         patch.object(m, "_check_vad", return_value=True), \
         patch.object(m, "asr_device_ok", return_value=True), \
         patch.object(m, "asr_device_name", return_value="cuda"):
        r = client.get("/api/models/services")
    assert r.status_code == 200
    body = r.json()
    # Alle vier Services sind im Matrix-Schlüssel vorhanden
    for key in ("asr", "vad", "diar", "aligner"):
        assert key in body, f"Service {key} fehlt in Matrix"
    assert body["asr"]["available"] is True
    assert body["asr"]["features"]["device"] == "cuda"
    assert body["vad"]["available"] is True
    assert body["diar"]["code"] == "ok"
    assert body["aligner"]["code"] == "ok"
    assert body["aligner"]["features"]["max_duration_s"] == 400.0
