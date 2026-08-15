"""API-Doku: /api-docs + /api/specs/<name>.json für alle Container."""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api_specs import ALIGNER_SPEC, build_specs
from app.routers.api_docs import router as api_docs_router


@pytest.fixture()
def client():
    app = FastAPI()
    app.include_router(api_docs_router)
    return TestClient(app)


def test_specs_decken_alle_container_ab():
    specs = build_specs()
    # Alle Backend-Container müssen dokumentiert sein
    for name in [
        "ps-pk-onnx", "crispr-pk-cpp", "crispr-qwen3",
        "crispr-moonshine-de", "crispr-ark", "crispr-canary",
        "crispr-diar", "crispr-align",
    ]:
        assert name in specs, f"Spec für {name} fehlt"


def test_alle_specs_sind_gueltige_openapi():
    for name, spec in build_specs().items():
        assert spec["openapi"].startswith("3.")
        assert "paths" in spec
        assert spec["info"]["title"]
        assert spec["servers"][0]["url"]


def test_asr_specs_haben_openai_endpoint():
    for name in ["ps-pk-onnx", "crispr-pk-cpp", "crispr-qwen3", "crispr-diar"]:
        spec = build_specs()[name]
        assert "/v1/audio/transcriptions" in spec["paths"]


def test_aligner_spec_hat_align_endpoint():
    assert "/v1/audio/align" in ALIGNER_SPEC["paths"]
    assert "/health" in ALIGNER_SPEC["paths"]


def test_get_spec_200(client):
    r = client.get("/api/specs/ps-pk-onnx.json")
    assert r.status_code == 200
    assert r.json()["info"]["title"] == "PolySchnack ASR (ONNX Parakeet)"


def test_get_spec_unknown_404(client):
    assert client.get("/api/specs/nope.json").status_code == 404


def test_api_docs_seite_rendert(client):
    r = client.get("/api-docs")
    assert r.status_code == 200
    assert "swagger-ui-bundle.js" in r.text
    assert "PolySchnack" in r.text
    # Alle Specs sind im HTML eingebettet (Client-seitige Auswahl)
    for name in ["ps-pk-onnx", "crispr-align"]:
        assert name in r.text


def test_webapp_openapi_schema_komplett():
    """Der frühere /openapi.json-500 (fehlender Optional-Import) darf nie
    zurückkommen: die komplette App-Schema-Generierung muss laufen."""
    from app.main import app

    schema = app.openapi()
    assert "/api-docs" not in schema["paths"]  # nicht im Schema (include_in_schema=False)
    assert "/api/specs/{name}.json" in schema["paths"]
