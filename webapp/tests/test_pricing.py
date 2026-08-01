"""Kostenpflichtige Pfade (Task B9) — cost_per_minute_eur → anon-Sperre."""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from app import pricing
from app.service_registry import SERVICES, get_service


class _Anon:
    kind = "anonymous"


class _Oidc:
    kind = "oidc"


def test_all_services_have_cost_field():
    for s in SERVICES:
        assert "cost_per_minute_eur" in s
        assert s["cost_per_minute_eur"] == 0.0  # aktuell alle lokal/kostenlos


def test_is_paid_backend(monkeypatch):
    monkeypatch.setattr(pricing, "get_service",
                        lambda name: {"cost_per_minute_eur": 0.02})
    assert pricing.is_paid_backend("x") is True
    monkeypatch.setattr(pricing, "get_service",
                        lambda name: {"cost_per_minute_eur": 0.0})
    assert pricing.is_paid_backend("x") is False
    monkeypatch.setattr(pricing, "get_service", lambda name: None)
    assert pricing.is_paid_backend("x") is False


def test_paid_route_for():
    assert pricing.paid_route_for(None) is False
    assert pricing.paid_route_for(_Anon()) is False
    assert pricing.paid_route_for(_Oidc()) is True


def test_ensure_free_only_anon_paid_backend_403(monkeypatch):
    monkeypatch.setattr(pricing, "get_service",
                        lambda name: {"cost_per_minute_eur": 0.02})
    with pytest.raises(HTTPException) as ei:
        pricing.ensure_free_only(_Anon(), backend="paid-backend")
    assert ei.value.status_code == 403


def test_ensure_free_only_anon_want_llm_403():
    with pytest.raises(HTTPException) as ei:
        pricing.ensure_free_only(_Anon(), want_llm=True)
    assert ei.value.status_code == 403


def test_ensure_free_only_anon_llm_mode_403():
    with pytest.raises(HTTPException) as ei:
        pricing.ensure_free_only(_Anon(), llm_mode=True)
    assert ei.value.status_code == 403


def test_ensure_free_only_anon_local_ok(monkeypatch):
    monkeypatch.setattr(pricing, "get_service",
                        lambda name: {"cost_per_minute_eur": 0.0})
    pricing.ensure_free_only(_Anon(), backend="pk-python")  # kein Raise


def test_ensure_free_only_oidc_paid_ok(monkeypatch):
    monkeypatch.setattr(pricing, "get_service",
                        lambda name: {"cost_per_minute_eur": 0.02})
    pricing.ensure_free_only(_Oidc(), backend="paid", want_llm=True)  # kein Raise
