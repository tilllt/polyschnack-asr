"""Hybrid GPU/CPU-Tests (Task A1): USE_GPU default auto + CUDA-Preload-Fallback.

Der ASR-Service muss auf Maschinen ohne GPU starten (CPU-Fallback), statt beim
CUDA-Preload hart zu crashen. onnxruntime/onnx_asr sind im Test-venv nicht
installiert -> werden als Fake-Module in sys.modules eingespielt.
"""
from __future__ import annotations

import importlib
import sys
import types

import pytest

import polyschnack_service.config as config


# ---------------------------------------------------------------------------
# Fake-Module für onnxruntime / onnx_asr (nicht im Test-venv installiert)
# ---------------------------------------------------------------------------
def _make_fake_ort():
    m = types.ModuleType("onnxruntime")
    m.__version__ = "0.0.0-fake"

    def preload_dlls(**kw):
        return None

    def get_available_providers():
        return ["CPUExecutionProvider"]

    m.preload_dlls = preload_dlls
    m.get_available_providers = get_available_providers
    m.SessionOptions = type("SessionOptions", (), {})
    m.ExecutionMode = type("ExecutionMode", (), {"ORT_SEQUENTIAL": 1})
    m.GraphOptimizationLevel = type(
        "GraphOptimizationLevel", (), {"ORT_ENABLE_ALL": 2}
    )
    return m


def _make_fake_onnx_asr():
    return types.ModuleType("onnx_asr")


@pytest.fixture()
def fake_ml_modules(monkeypatch):
    """Setzt Fake-Module VOR dem ersten model-Import in sys.modules.

    WICHTIG: model.ort referenziert das Modul-Objekt vom Import-Zeitpunkt —
    pro Test ein NEUES Fake-Modul zu erzeugen würde die Patches ins Leere
    laufen lassen (model.ort zeigt auf das alte Objekt). Deshalb hier das
    Fake-Modul einmal erzeugen und nur die preload_dlls-Funktion pro Test
    direkt auf model.ort gepatcht.
    """
    fake_ort = _make_fake_ort()
    monkeypatch.setitem(sys.modules, "onnxruntime", fake_ort)
    monkeypatch.setitem(sys.modules, "onnx_asr", _make_fake_onnx_asr())
    return fake_ort


def _reload_config(monkeypatch):
    """Config frisch laden (ohne Env-Manipulation — Env steuert der Test)."""
    return importlib.reload(config)


def _clear_gpu_env(monkeypatch):
    for var in ("POLYSCHNACK_USE_GPU", "POLYSNACK_USE_GPU", "PARAKEET_USE_GPU"):
        monkeypatch.delenv(var, raising=False)


# ---------------------------------------------------------------------------
# USE_GPU-Default
# ---------------------------------------------------------------------------
def test_use_gpu_defaults_to_auto(monkeypatch):
    _clear_gpu_env(monkeypatch)
    cfg = _reload_config(monkeypatch)
    assert cfg.USE_GPU == "auto"


def test_use_gpu_explicit_true_wins(monkeypatch):
    _clear_gpu_env(monkeypatch)
    monkeypatch.setenv("POLYSCHNACK_USE_GPU", "true")
    cfg = _reload_config(monkeypatch)
    assert cfg.USE_GPU == "true"


def test_use_gpu_explicit_false_wins(monkeypatch):
    _clear_gpu_env(monkeypatch)
    monkeypatch.setenv("POLYSCHNACK_USE_GPU", "false")
    cfg = _reload_config(monkeypatch)
    assert cfg.USE_GPU == "false"


# ---------------------------------------------------------------------------
# CUDA-Preload: Fehler darf nie hart crashen (Hybrid-Prinzip)
# ---------------------------------------------------------------------------
def test_preload_cuda_failure_falls_back_to_cpu(fake_ml_modules, monkeypatch):
    """Preload-Fehler -> Warnung + CPU-Fallback, KEIN RuntimeError (auch bei auto)."""
    from polyschnack_service import model

    model._CUDA_PRELOADED = False
    monkeypatch.setattr(model, "USE_GPU", "auto")

    def boom(**kw):
        raise RuntimeError("no CUDA driver")

    # Direkt auf model.ort patchen — das Modul-Objekt, das model beim Import
    # referenziert hat (sys.modules-Patch allein reicht nicht).
    monkeypatch.setattr(model.ort, "preload_dlls", boom)

    # Darf nicht werfen:
    model._preload_cuda_libraries()
    assert model._CUDA_PRELOADED is True


def test_preload_cuda_failure_even_true_does_not_raise(fake_ml_modules, monkeypatch):
    """Auch bei explizitem USE_GPU=true kein harter Crash — Hybrid-Prinzip
    (Log-Warnung reicht; der ORT-Provider-Fallback übernimmt)."""
    from polyschnack_service import model

    model._CUDA_PRELOADED = False
    monkeypatch.setattr(model, "USE_GPU", "true")

    def boom(**kw):
        raise RuntimeError("no CUDA driver")

    monkeypatch.setattr(model.ort, "preload_dlls", boom)

    model._preload_cuda_libraries()
    assert model._CUDA_PRELOADED is True


def test_preload_cuda_skipped_when_use_gpu_false(fake_ml_modules, monkeypatch):
    from polyschnack_service import model

    model._CUDA_PRELOADED = False
    monkeypatch.setattr(model, "USE_GPU", "false")

    model._preload_cuda_libraries()
    assert model._CUDA_PRELOADED is False  # nie versucht
