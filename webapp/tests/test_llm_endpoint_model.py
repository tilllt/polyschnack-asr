"""BYOK (Task E1) — SSRF-Validierung + UserLlmEndpoint (Key verschlüsselt)."""
from __future__ import annotations

import pytest
from fastapi import HTTPException
from sqlmodel import Session, SQLModel, create_engine

from app import crypto
from app.llm_url import validate_llm_url
from app.models import UserLlmEndpoint


def test_validate_public_url_ok():
    assert validate_llm_url("https://api.mistral.ai/v1") == "https://api.mistral.ai/v1"


def test_validate_rejects_localhost():
    with pytest.raises(HTTPException) as ei:
        validate_llm_url("http://localhost:8080/v1")
    assert ei.value.status_code == 422


def test_validate_rejects_private_ip():
    with pytest.raises(HTTPException) as ei:
        validate_llm_url("https://10.0.0.5/v1")
    assert ei.value.status_code == 422


def test_validate_rejects_metadata():
    with pytest.raises(HTTPException) as ei:
        validate_llm_url("http://169.254.169.254/latest/meta-data")
    assert ei.value.status_code == 422


def test_validate_rejects_non_http():
    with pytest.raises(HTTPException) as ei:
        validate_llm_url("file:///etc/passwd")
    assert ei.value.status_code == 422


def test_validate_rejects_link_local():
    with pytest.raises(HTTPException) as ei:
        validate_llm_url("http://[fe80::1]/v1")
    assert ei.value.status_code == 422


def test_endpoint_roundtrip():
    """api_key wird verschlüsselt gespeichert; decrypt liefert den Klartext."""
    eng = create_engine("sqlite://")
    SQLModel.metadata.create_all(eng)
    with Session(eng) as s:
        ep = UserLlmEndpoint(user_id=1, name="mistral", base_url="https://api.mistral.ai/v1",
                             api_key=crypto.encrypt("sk-1234"), model="mistral-small-latest")
        s.add(ep)
        s.commit()
        ep_id = ep.id
    with Session(eng) as s:
        ep = s.get(UserLlmEndpoint, ep_id)
        assert ep.api_key != "sk-1234"
        assert crypto.decrypt(ep.api_key) == "sk-1234"
