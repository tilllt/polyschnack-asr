"""Service-Registry-Tests (Task 2)."""
from __future__ import annotations

import pytest

from app.asr_client import get_client
from app.service_registry import (
    SERVICES,
    available_services,
    get_service,
    list_services,
    total_concurrency,
)


def test_list_services_returns_all():
    assert len(list_services()) == len(SERVICES) >= 4


def test_get_service_by_name_and_backend():
    assert get_service("pk-python")["compose_profile"] == "default"
    assert get_service("qwen3-asr")["backend"] == "qwen3-asr"
    assert get_service("does-not-exist") is None


def test_required_fields_present():
    for s in SERVICES:
        assert s["type"] in {"local", "remote"}
        assert s["concurrency"] >= 1
        for k in ("vram_gb", "ram_gb", "disk_gb"):
            assert s["requires"][k] >= 0
        for k in ("word_timestamps", "streaming", "async_jobs", "noise_reduce",
                  "vad", "diarization", "enhance", "languages", "device"):
            assert k in s["capabilities"]


def test_local_services_have_valid_profile():
    valid = {"default", "cpp", "qwen3", "ark", "voxtral", "moonshine", "canary"}
    for s in SERVICES:
        if s["type"] == "local":
            assert s["compose_profile"] in valid


def test_moonshine_de_service_registered():
    svc = get_service("moonshine-de")
    assert svc is not None
    assert svc["container_name"] == "polyschnack-moonshine-de"
    assert svc["url"] == "http://polyschnack-moonshine-de:8080"
    assert svc["compose_profile"] == "moonshine"
    assert svc["capabilities"]["languages"] == ["de"]


def test_canary_asr_service_registered():
    svc = get_service("canary-asr")
    assert svc is not None
    assert svc["container_name"] == "polyschnack-canary"
    assert svc["url"] == "http://polyschnack-canary:8080"
    assert svc["compose_profile"] == "canary"
    assert set(svc["capabilities"]["languages"]) == {"de", "en", "fr", "es"}


def test_default_backend_adapter_matches_registry():
    """Registry is documentation, the adapter is truth — they must agree."""
    client = get_client()
    reg = get_service(client.capabilities.label) or get_service("pk-python")
    caps = client.capabilities
    assert caps.streaming == (reg["capabilities"]["streaming"] is True)
    assert caps.async_jobs == (reg["capabilities"]["async_jobs"] is True)
    assert caps.noise_reduce == (reg["capabilities"]["noise_reduce"] is True)


def test_available_services_only_active():
    assert all(s["status"] == "active" for s in available_services())
    assert len(available_services()) <= len(SERVICES)


def test_total_concurrency_is_sum_of_capacities():
    assert total_concurrency() == sum(s["concurrency"] for s in available_services())
    assert total_concurrency() >= 1
