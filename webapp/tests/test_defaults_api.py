"""Change 228 — Vorgabewerte je Nutzer + Modellliste des Providers.

Geprüft wird:
- ``GET /api/defaults`` ohne Zeile: Standardwerte, ``configured=false``.
- ``PUT /api/defaults``: Rückschreiben, gezieltes Leeren (``null``), ein
  weggelassener Schlüssel lässt den Wert stehen.
- Zugehörigkeit: fremde Vorlage/Endpunkt/Ziel → 404 (kein Rückschluss).
- Obergrenze der Optionswerte → 413.
- ``POST /api/llm-endpoints/models``: Erfolg (sortiert, doppelfrei),
  Fehler mit Klartext statt stiller Leere, kein Provider, BYOK-Endpunkt
  benutzt den entschlüsselten Schlüssel, fremder Endpunkt → 404.
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException
from sqlmodel import Session, SQLModel, create_engine, select

from app import crypto
from app.models import (
    DeliveryTarget,
    PromptTemplate,
    User,
    UserDefaults,
    UserLlmEndpoint,
)
from app.routers import defaults as defaults_api
from app.routers import llm_endpoints as llm_api


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
        s.add(PromptTemplate(id=10, user_id=1, name="eigene", prompt="p"))
        s.add(PromptTemplate(id=11, user_id=2, name="fremde", prompt="p"))
        s.add(UserLlmEndpoint(id=20, user_id=1, name="eigener",
                              base_url="https://example.com/v1",
                              api_key=crypto.encrypt("sk-geheim"), model="m"))
        s.add(UserLlmEndpoint(id=21, user_id=2, name="fremder",
                              base_url="https://example.com/v1",
                              api_key=crypto.encrypt("sk-fremd"), model="m"))
        s.add(DeliveryTarget(id=30, user_id=1, name="mein Ziel", kind="email"))
        s.add(DeliveryTarget(id=31, user_id=2, name="fremdes Ziel", kind="email"))
        s.commit()
    return eng


@pytest.fixture(autouse=True)
def _as_user(monkeypatch):
    """Identität aus dem Fake-Request, für beide Router."""
    monkeypatch.setattr(defaults_api, "_current_user",
                        lambda request, session=None: request.session.get("user_id"))
    monkeypatch.setattr(llm_api, "_current_user",
                        lambda request, session=None: request.session.get("user_id"))


# --------------------------------------------------------------- Vorgabewerte

def test_get_without_row_returns_standard(db):
    with Session(db) as s:
        out = defaults_api.get_defaults(_req(1), s)
    assert out["default_source"] == "upload"
    assert out["default_options"] is None
    assert out["default_template_id"] is None
    assert out["default_endpoint_id"] is None
    assert out["default_target_id"] is None
    assert out["configured"] is False


def test_put_and_get_roundtrip(db):
    opts = {"vad": True, "diarize": True, "model": "gross", "num": 3}
    with Session(db) as s:
        out = defaults_api.put_defaults(
            defaults_api.DefaultsUpdate(default_source="record", default_options=opts,
                                        default_template_id=10, default_endpoint_id=20,
                                        default_target_id=30), _req(1), s)
    assert out["default_source"] == "record"
    assert out["default_options"] == opts
    assert (out["default_template_id"], out["default_endpoint_id"], out["default_target_id"]) == (10, 20, 30)
    assert out["configured"] is True
    with Session(db) as s:
        again = defaults_api.get_defaults(_req(1), s)
        assert again == out


def test_omitted_key_keeps_value_and_null_clears(db):
    with Session(db) as s:
        defaults_api.put_defaults(
            defaults_api.DefaultsUpdate(default_options={"vad": False}, default_target_id=30),
            _req(1), s)
    # Schlüssel weggelassen → Wert bleibt
    with Session(db) as s:
        out = defaults_api.put_defaults(defaults_api.DefaultsUpdate(default_source="url"), _req(1), s)
    assert out["default_options"] == {"vad": False}
    assert out["default_target_id"] == 30
    assert out["default_source"] == "url"
    # ausdrücklich null → geleert
    with Session(db) as s:
        out = defaults_api.put_defaults(
            defaults_api.DefaultsUpdate(default_target_id=None), _req(1), s)
    assert out["default_target_id"] is None
    assert out["default_options"] == {"vad": False}


def test_foreign_ids_are_rejected(db):
    cases = [
        {"default_template_id": 11},
        {"default_endpoint_id": 21},
        {"default_target_id": 31},
    ]
    for payload in cases:
        with Session(db) as s:
            with pytest.raises(HTTPException) as exc:
                defaults_api.put_defaults(defaults_api.DefaultsUpdate(**payload), _req(1), s)
        assert exc.value.status_code == 404, payload
    # Nichts wurde geschrieben.
    with Session(db) as s:
        assert s.exec(select(UserDefaults)).first() is None


def test_only_one_row_per_user(db):
    with Session(db) as s:
        defaults_api.put_defaults(defaults_api.DefaultsUpdate(default_source="record"), _req(1), s)
    with Session(db) as s:
        defaults_api.put_defaults(defaults_api.DefaultsUpdate(default_source="url"), _req(1), s)
    with Session(db) as s:
        rows = s.exec(select(UserDefaults).where(UserDefaults.user_id == 1)).all()
    assert len(rows) == 1 and rows[0].default_source == "url"


def test_options_size_is_bounded(db):
    with Session(db) as s:
        with pytest.raises(HTTPException) as exc:
            defaults_api.put_defaults(
                defaults_api.DefaultsUpdate(default_options={"x": "y" * 20_001}), _req(1), s)
    assert exc.value.status_code == 413


def test_delete_clears_everything(db):
    with Session(db) as s:
        defaults_api.put_defaults(defaults_api.DefaultsUpdate(default_source="record"), _req(1), s)
    with Session(db) as s:
        out = defaults_api.delete_defaults(_req(1), s)
    assert out["configured"] is False and out["default_source"] == "upload"


# ------------------------------------------------------------- Modellliste

class _FakeResponse:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


def test_models_ok_sorted_and_unique(db, monkeypatch):
    seen = {}

    def fake_get(url, headers=None, timeout=None):
        seen["url"] = url
        seen["headers"] = headers or {}
        return _FakeResponse({"data": [{"id": "b"}, {"id": "a"}, {"id": "a"}, {"nope": 1}]})

    monkeypatch.setattr(llm_api.httpx, "get", fake_get)
    with Session(db) as s:
        out = llm_api.list_provider_models(
            llm_api.ModelsQuery(base_url="https://example.com/v1", api_key="sk-k"), _req(1), s)
    assert out["ok"] is True
    assert out["models"] == ["a", "b"]
    assert out["count"] == 2
    assert seen["url"] == "https://example.com/v1/models"
    assert seen["headers"]["Authorization"] == "Bearer sk-k"


def test_models_byok_uses_decrypted_key(db, monkeypatch):
    seen = {}

    def fake_get(url, headers=None, timeout=None):
        seen["headers"] = headers or {}
        return _FakeResponse({"data": [{"id": "m-1"}]})

    monkeypatch.setattr(llm_api.httpx, "get", fake_get)
    with Session(db) as s:
        out = llm_api.list_provider_models(llm_api.ModelsQuery(endpoint_id=20), _req(1), s)
    assert out["ok"] is True and out["source"] == "byok"
    assert seen["headers"]["Authorization"] == "Bearer sk-geheim"


def test_models_foreign_endpoint_404(db, monkeypatch):
    monkeypatch.setattr(llm_api.httpx, "get",
                        lambda *a, **k: _FakeResponse({"data": []}))
    with Session(db) as s:
        with pytest.raises(HTTPException) as exc:
            llm_api.list_provider_models(llm_api.ModelsQuery(endpoint_id=21), _req(1), s)
    assert exc.value.status_code == 404


def test_models_error_is_visible_not_silent(db, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("Connection refused")

    monkeypatch.setattr(llm_api.httpx, "get", boom)
    with Session(db) as s:
        out = llm_api.list_provider_models(
            llm_api.ModelsQuery(base_url="https://example.com/v1", api_key="k"), _req(1), s)
    assert out["ok"] is False
    assert out["models"] == []
    assert "Connection refused" in out["error"]
    assert "k" not in out["error"]  # Schlüssel taucht nie in der Meldung auf


def test_models_without_provider(db, monkeypatch):
    monkeypatch.setattr(llm_api.settings, "POLYSCHNACK_LLM_URL", "")
    with Session(db) as s:
        out = llm_api.list_provider_models(llm_api.ModelsQuery(), _req(1), s)
    assert out["ok"] is False
    assert "kein Provider konfiguriert" in out["error"]
