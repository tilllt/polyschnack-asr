"""Env-Präfix-Tests (Task 0): POLYSCHNACK_* gewinnt, POLYSNACK_*/PARAKEET_* als Legacy-Fallback.

Die App heißt PolySchnack — der Env-Präfix wurde auf POLYSCHNACK_* vereinheitlicht.
Alte Deployments (compose, Harbor, systemd) mit POLYSNACK_*/PARAKEET_* müssen
weiter funktionieren (mit Deprecation-Warning).
"""
from __future__ import annotations

from polyschnack_service import config


def test_new_prefix_wins(monkeypatch):
    monkeypatch.setenv("POLYSCHNACK_X", "new")
    monkeypatch.setenv("POLYSNACK_X", "old")
    monkeypatch.setenv("PARAKEET_X", "ancient")
    assert config._getenv("X") == "new"


def test_legacy_polysnack_fallback(monkeypatch):
    monkeypatch.delenv("POLYSCHNACK_X", raising=False)
    monkeypatch.setenv("POLYSNACK_X", "old")
    monkeypatch.delenv("PARAKEET_X", raising=False)
    assert config._getenv("X") == "old"


def test_legacy_parakeet_fallback(monkeypatch):
    monkeypatch.delenv("POLYSCHNACK_X", raising=False)
    monkeypatch.delenv("POLYSNACK_X", raising=False)
    monkeypatch.setenv("PARAKEET_X", "ancient")
    assert config._getenv("X") == "ancient"


def test_default_when_nothing_set(monkeypatch):
    monkeypatch.delenv("POLYSCHNACK_X", raising=False)
    monkeypatch.delenv("POLYSNACK_X", raising=False)
    monkeypatch.delenv("PARAKEET_X", raising=False)
    assert config._getenv("X", "dflt") == "dflt"
