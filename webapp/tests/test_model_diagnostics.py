"""Diagnose-Check für Modell-Ladefehler (TDD).

Erwartung: /api/models/status liefert detaillierte Fehlerursachen statt nur
bool-Flags — unterscheidet 404 (Repo existiert nicht), 401 (Token fehlt/ungültig),
403 (gated, Bedingungen nicht akzeptiert), Netzwerkfehler und fehlende Pakete.
"""
import json
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _probe_repo(repo_id: str, token: str | None) -> dict:
    """Prüft Erreichbarkeit eines HF-Repos per API-Call (schnell, kein Download).

    Liefert {status, code, message, repo}. Codes: ok / no-token / unauthorized /
    gated / not-found / network-error.
    """
    from app.routers import models as m

    return m._probe_repo(repo_id, token)


# ---------------------------------------------------------------------------
# _probe_repo: HTTP-Status-Mapping
# ---------------------------------------------------------------------------

def test_probe_repo_ok():
    with patch("httpx.get") as mock_get:
        resp = MagicMock(status_code=200)
        resp.raise_for_status.return_value = None
        mock_get.return_value = resp
        r = _probe_repo("org/repo", "hf_x")
        assert r["code"] == "ok"
        assert r["status"] == 200


def test_probe_repo_uses_raw_slash_url():
    """HF-API lehnt %2F-encoded Repo-Pfade mit 400 ab — der Probe-Call muss
    den Slash unverändert lassen (https://huggingface.co/api/models/org/repo)."""
    with patch("httpx.get") as mock_get:
        resp = MagicMock(status_code=200)
        resp.raise_for_status.return_value = None
        mock_get.return_value = resp
        _probe_repo("pyannote/speaker-diarization-3.1", "hf_x")
        args, kwargs = mock_get.call_args
        url = args[0]
        assert "%2F" not in url
        assert url.endswith("/pyannote/speaker-diarization-3.1")


def test_probe_repo_404_not_found():
    with patch("httpx.get") as mock_get:
        resp = MagicMock(status_code=404)
        mock_get.return_value = resp
        r = _probe_repo("org/does-not-exist", "hf_x")
        assert r["code"] == "not-found"
        assert "existiert nicht" in r["message"]


def test_probe_repo_403_gated():
    with patch("httpx.get") as mock_get:
        resp = MagicMock(status_code=403)
        mock_get.return_value = resp
        r = _probe_repo("org/gated-model", "hf_x")
        assert r["code"] == "gated"
        assert "Nutzungsbedingungen" in r["message"]


def test_probe_repo_401_unauthorized():
    with patch("httpx.get") as mock_get:
        resp = MagicMock(status_code=401)
        mock_get.return_value = resp
        r = _probe_repo("org/private", "hf_invalid")
        assert r["code"] == "unauthorized"
        assert "Token" in r["message"]


def test_probe_repo_no_token():
    r = _probe_repo("org/repo", None)
    assert r["code"] == "no-token"
    assert r["status"] is None


def test_probe_repo_network_error():
    with patch("httpx.get", side_effect=Exception("connection refused")):
        r = _probe_repo("org/repo", "hf_x")
        assert r["code"] == "network-error"


# ---------------------------------------------------------------------------
# _diarize_diagnosis: Zusammenfassung der Pipeline-Komponenten
# ---------------------------------------------------------------------------

def test_diarize_diagnosis_no_token():
    from app.routers import models as m

    with patch.object(m, "_hf_token", return_value=False), \
         patch.object(m, "_pyannote_importable", return_value=True):
        d = m._diarize_diagnosis()
        assert d["available"] is False
        assert d["code"] == "no-token"
        assert "HF_TOKEN" in d["message"]


def test_diarize_diagnosis_pyannote_missing():
    from app.routers import models as m

    with patch.object(m, "_hf_token", return_value=True), \
         patch.object(m, "_pyannote_importable", return_value=False):
        d = m._diarize_diagnosis()
        assert d["available"] is False
        assert d["code"] == "pyannote-missing"
        assert "pyannote" in d["message"].lower()


def test_diarize_diagnosis_gated_repo_detected():
    """Wenn eines der Komponenten-Repos 403 liefert, wird genau das gemeldet."""
    from app.routers import models as m

    ok_resp = MagicMock(status_code=200)
    ok_resp.raise_for_status.return_value = None
    gated_resp = MagicMock(status_code=403)

    def fake_probe(repo_id, token):
        if repo_id == "pyannote/speaker-diarization-community-1":
            return {"status": 403, "code": "gated", "repo": repo_id,
                    "message": "gated"}
        return {"status": 200, "code": "ok", "repo": repo_id, "message": ""}

    with patch.object(m, "_hf_token", return_value=True), \
         patch.object(m, "_pyannote_importable", return_value=True), \
         patch.object(m, "_probe_repo", side_effect=fake_probe):
        d = m._diarize_diagnosis()
        assert d["available"] is False
        assert d["code"] == "gated"
        assert "speaker-diarization-community-1" in d["repo"]


def test_diarize_diagnosis_all_ok():
    from app.routers import models as m

    ok_resp = MagicMock(status_code=200)
    ok_resp.raise_for_status.return_value = None

    with patch.object(m, "_hf_token", return_value=True), \
         patch.object(m, "_pyannote_importable", return_value=True), \
         patch.object(m, "_probe_repo", return_value={"status": 200, "code": "ok",
                                                       "repo": "x", "message": ""}):
        d = m._diarize_diagnosis()
        assert d["available"] is True
        assert d["code"] == "ok"


# ---------------------------------------------------------------------------
# /api/models/status: neue Detail-Felder
# ---------------------------------------------------------------------------

def test_status_endpoint_has_diag_fields():
    from app.routers import models as m

    with patch.object(m, "_hf_token", return_value=True), \
         patch.object(m, "_pyannote_importable", return_value=True), \
         patch.object(m, "_probe_repo", return_value={"status": 200, "code": "ok",
                                                       "repo": "x", "message": ""}), \
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
        assert "vad_diag" in body
        assert body["diarize_diag"]["code"] == "ok"


def test_status_endpoint_reports_gated():
    from app.routers import models as m

    with patch.object(m, "_hf_token", return_value=True), \
         patch.object(m, "_pyannote_importable", return_value=True), \
         patch.object(m, "_probe_repo", return_value={"status": 403, "code": "gated",
                                                       "repo": "pyannote/x",
                                                       "message": "gated"}), \
         patch("app.routers.models.httpx.get") as mock_httpx:
        resp = MagicMock(status_code=200)
        resp.raise_for_status.return_value = None
        resp.json.return_value = {"device": "cuda"}
        mock_httpx.return_value = resp

        r = client.get("/api/models/status")
        body = r.json()
        assert body["diarize_available"] is False
        assert body["diarize_diag"]["code"] == "gated"
