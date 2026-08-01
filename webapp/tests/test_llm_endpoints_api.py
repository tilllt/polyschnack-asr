"""BYOK-CRUD-API (Task E2) — Key maskiert, nur OIDC, SSRF-blockiert."""
from __future__ import annotations

import pytest
from fastapi import HTTPException
from sqlmodel import Session, SQLModel, create_engine

from app import crypto
from app.models import User, UserLlmEndpoint
from app.routers import llm_endpoints


class _FakeRequest:
    def __init__(self, session=None):
        self.session = session or {}


def _req(uid=None):
    return _FakeRequest(session={"user_id": uid} if uid is not None else {})


@pytest.fixture()
def db():
    eng = create_engine("sqlite://")
    SQLModel.metadata.create_all(eng)
    with Session(eng) as s:
        s.add(User(id=1, sub="a", kind="oidc"))
        s.add(User(id=2, sub="b", kind="oidc"))
        s.add(User(id=3, sub="anon", kind="anonymous"))
        s.commit()
    return eng


def test_create_and_list_masks_key(db, monkeypatch):
    monkeypatch.setattr(llm_endpoints, "_current_user",
                        lambda request, session=None: request.session.get("user_id"))
    with Session(db) as s:
        out = llm_endpoints.create_endpoint(
            llm_endpoints.EndpointCreate(name="mistral", base_url="https://api.mistral.ai/v1",
                                         api_key="sk-1234", model="mistral-small-latest"),
            _req(1), s)
        assert "api_key" not in out
        ep = s.exec(__import__("sqlmodel").select(UserLlmEndpoint)).first()
        assert ep.api_key != "sk-1234"
        assert crypto.decrypt(ep.api_key) == "sk-1234"
        lst = llm_endpoints.list_endpoints(_req(1), s)
        assert lst[0]["name"] == "mistral"


def test_update_keeps_key_when_omitted(db, monkeypatch):
    monkeypatch.setattr(llm_endpoints, "_current_user",
                        lambda request, session=None: request.session.get("user_id"))
    with Session(db) as s:
        ep = UserLlmEndpoint(user_id=1, name="a", base_url="https://api.mistral.ai/v1",
                             api_key=crypto.encrypt("sk-alt"), model="m")
        s.add(ep)
        s.commit()
        eid = ep.id
    with Session(db) as s:
        llm_endpoints.update_endpoint(
            eid, llm_endpoints.EndpointUpdate(name="neu"), _req(1), s)
    with Session(db) as s:
        ep = s.get(UserLlmEndpoint, eid)
        assert ep.name == "neu"
        assert crypto.decrypt(ep.api_key) == "sk-alt"


def test_update_replaces_key(db, monkeypatch):
    monkeypatch.setattr(llm_endpoints, "_current_user",
                        lambda request, session=None: request.session.get("user_id"))
    with Session(db) as s:
        ep = UserLlmEndpoint(user_id=1, name="a", base_url="https://api.mistral.ai/v1",
                             api_key=crypto.encrypt("sk-alt"), model="m")
        s.add(ep)
        s.commit()
        eid = ep.id
    with Session(db) as s:
        llm_endpoints.update_endpoint(
            eid, llm_endpoints.EndpointUpdate(api_key="sk-neu"), _req(1), s)
    with Session(db) as s:
        assert crypto.decrypt(s.get(UserLlmEndpoint, eid).api_key) == "sk-neu"


def test_foreign_endpoint_404(db, monkeypatch):
    monkeypatch.setattr(llm_endpoints, "_current_user",
                        lambda request, session=None: request.session.get("user_id"))
    with Session(db) as s:
        ep = UserLlmEndpoint(user_id=2, name="fremd", base_url="https://api.openai.com/v1",
                             api_key=crypto.encrypt("x"), model="m")
        s.add(ep)
        s.commit()
        eid = ep.id
    with Session(db) as s:
        with pytest.raises(HTTPException) as ei:
            llm_endpoints.update_endpoint(
                eid, llm_endpoints.EndpointUpdate(name="hack"), _req(1), s)
        assert ei.value.status_code == 404


def test_anonymous_403(db, monkeypatch):
    monkeypatch.setattr(llm_endpoints, "_current_user",
                        lambda request, session=None: request.session.get("user_id"))
    with Session(db) as s:
        with pytest.raises(HTTPException) as ei:
            llm_endpoints.create_endpoint(
                llm_endpoints.EndpointCreate(name="x", base_url="https://api.mistral.ai/v1",
                                             api_key="sk"), _req(3), s)
        assert ei.value.status_code == 403


def test_invalid_url_422(db, monkeypatch):
    monkeypatch.setattr(llm_endpoints, "_current_user",
                        lambda request, session=None: request.session.get("user_id"))
    with Session(db) as s:
        with pytest.raises(HTTPException) as ei:
            llm_endpoints.create_endpoint(
                llm_endpoints.EndpointCreate(name="x", base_url="http://localhost:8080/v1",
                                             api_key="sk"), _req(1), s)
        assert ei.value.status_code == 422
