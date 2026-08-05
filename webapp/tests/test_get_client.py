"""Factory-Tests: crispr-moonshine-de + crispr-canary Backend-Durchstich (Task C6)."""
from __future__ import annotations

import pytest

from app.asr_client import BackendCapabilities, get_client
from app.asr_client.adapters.crisp_asr_http import CrispAsrHttpClient


@pytest.fixture(autouse=True)
def _fresh_client_instance(monkeypatch):
    """Kein Singleton-Carry-Over zwischen Tests (get_client cached global)."""
    import app.asr_client as mod

    monkeypatch.setattr(mod, "_client_instance", None)
    yield
    monkeypatch.setattr(mod, "_client_instance", None)


def test_get_client_moonshine_de():
    c = get_client("crispr-moonshine-de")
    assert isinstance(c, CrispAsrHttpClient)
    assert c.capabilities.label == "crispr-moonshine-de"
    assert c.capabilities.languages == ["de"]
    assert c.capabilities.device == ["gpu", "cpu"]
    assert c.capabilities.native_punctuation is True
    assert c.url == "http://crispr-moonshine-de:5096"


def test_get_client_canary_asr():
    c = get_client("crispr-canary")
    assert isinstance(c, CrispAsrHttpClient)
    assert c.capabilities.label == "crispr-canary"
    assert set(c.capabilities.languages) == {"de", "en", "fr", "es"}
    assert c.capabilities.device == ["gpu", "cpu"]
    assert c.url == "http://crispr-canary:5097"


def test_get_client_url_env_override(monkeypatch):
    monkeypatch.setenv("MOONSHINE_URL", "http://moonshine-test:9999")
    c = get_client("crispr-moonshine-de")
    assert c.url == "http://moonshine-test:9999"


def test_crisp_client_capabilities_override():
    caps = BackendCapabilities(
        streaming=False, async_jobs=False, noise_reduce=False,
        word_timestamps=True, languages=["de"], device=["gpu", "cpu"],
        label="crispr-moonshine-de", native_punctuation=True,
    )
    c = CrispAsrHttpClient(url="http://override:8080", capabilities=caps)
    assert c.capabilities.label == "crispr-moonshine-de"
    assert c.capabilities.languages == ["de"]
    assert c.url == "http://override:8080"


def test_crisp_client_default_capabilities_still_ark():
    c = CrispAsrHttpClient(url="http://x:8080")
    assert c.capabilities.label == "crispr-ark"
    assert c.capabilities.native_punctuation is True


def test_ark_backend_unchanged():
    c = get_client("crispr-ark")
    assert c.capabilities.label == "crispr-ark"
    assert c.capabilities.languages == ["de", "en"]
