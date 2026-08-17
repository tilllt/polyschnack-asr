"""CUDA-Provider-Optionen (OOM-Schutz, 2026-08-17 Box).

Ursache auf der Box: cudnn_conv_use_max_workspace=1 liess cuDNN den GESAMTEN
freien VRAM als Workspace reservieren. Lief parallel der Aligner (qwen3 0.6B)
oder Diar, blieb für ONNX-Concat-Nodes kein Speicher mehr:
"Failed to allocate memory for requested buffer of size 9359104".

Fix: Defaults auf begrenzten Workspace (0), HEURISTIC-Suche statt EXHAUSTIVE,
Arena wächst in kleinen Schritten (kSameAsRequested), optional hartes
gpu_mem_limit in GB. Diese Tests sichern die Defaults gegen Regression.
"""
from __future__ import annotations

import importlib
import sys
import types

import pytest

import polyschnack_service.config as config


def _make_fake_ort():
    m = types.ModuleType("onnxruntime")
    m.__version__ = "0.0.0-fake"

    def get_available_providers():
        return ["CUDAExecutionProvider", "CPUExecutionProvider"]

    m.preload_dlls = lambda **kw: None
    m.get_available_providers = get_available_providers
    m.SessionOptions = type("SessionOptions", (), {})
    m.ExecutionMode = type("ExecutionMode", (), {"ORT_SEQUENTIAL": 1})
    m.GraphOptimizationLevel = type(
        "GraphOptimizationLevel", (), {"ORT_ENABLE_ALL": 2}
    )
    return m


@pytest.fixture()
def fake_ml_modules(monkeypatch):
    fake_ort = _make_fake_ort()
    monkeypatch.setitem(sys.modules, "onnxruntime", fake_ort)
    monkeypatch.setitem(sys.modules, "onnx_asr", types.ModuleType("onnx_asr"))
    return fake_ort


def _reload_config(monkeypatch):
    return importlib.reload(config)


def _clear_env(monkeypatch):
    for var in (
        "POLYSCHNACK_USE_GPU", "POLYSNACK_USE_GPU", "PARAKEET_USE_GPU",
        "POLYSCHNACK_CUDNN_MAX_WORKSPACE", "POLYSCHNACK_CUDNN_ALGO_SEARCH",
        "POLYSCHNACK_ORT_ARENA_EXTEND", "POLYSCHNACK_ORT_GPU_MEM_LIMIT_GB",
    ):
        monkeypatch.delenv(var, raising=False)


# ---------------------------------------------------------------------------
# Defaults: der eigentliche OOM-Fix
# ---------------------------------------------------------------------------
def test_cuda_defaults_bound_workspace(fake_ml_modules, monkeypatch):
    """Default: begrenzter cuDNN-Workspace + HEURISTIC + kleine Arena-Schritte."""
    _clear_env(monkeypatch)
    monkeypatch.setenv("POLYSCHNACK_USE_GPU", "true")
    _reload_config(monkeypatch)

    from polyschnack_service import model
    importlib.reload(model)
    model._CUDA_PRELOADED = False

    providers = model._resolve_providers()
    assert providers[0][0] == "CUDAExecutionProvider"
    opts = providers[0][1]
    # Der OOM-Fix: NIE mehr den ganzen VRAM als cuDNN-Workspace schnappen
    assert opts["cudnn_conv_use_max_workspace"] == "0"
    assert opts["cudnn_conv_algo_search"] == "HEURISTIC"
    assert opts["arena_extend_strategy"] == "kSameAsRequested"
    assert "gpu_mem_limit" not in opts  # Default: kein hartes Limit


def test_cuda_max_workspace_env_override(fake_ml_modules, monkeypatch):
    """Explizite Env-Werte gewinnen (auch Legacy-Präfix)."""
    _clear_env(monkeypatch)
    monkeypatch.setenv("POLYSCHNACK_USE_GPU", "true")
    monkeypatch.setenv("POLYSNACK_CUDNN_MAX_WORKSPACE", "1")  # Legacy-Fallback
    monkeypatch.setenv("POLYSCHNACK_CUDNN_ALGO_SEARCH", "EXHAUSTIVE")
    _reload_config(monkeypatch)

    from polyschnack_service import model
    importlib.reload(model)
    model._CUDA_PRELOADED = False

    providers = model._resolve_providers()
    opts = providers[0][1]
    assert opts["cudnn_conv_use_max_workspace"] == "1"
    assert opts["cudnn_conv_algo_search"] == "EXHAUSTIVE"


def test_cuda_gpu_mem_limit_gb(fake_ml_modules, monkeypatch):
    """POLYSCHNACK_ORT_GPU_MEM_LIMIT_GB setzt gpu_mem_limit in Bytes."""
    _clear_env(monkeypatch)
    monkeypatch.setenv("POLYSCHNACK_USE_GPU", "true")
    monkeypatch.setenv("POLYSCHNACK_ORT_GPU_MEM_LIMIT_GB", "12")
    _reload_config(monkeypatch)

    from polyschnack_service import model
    importlib.reload(model)
    model._CUDA_PRELOADED = False

    providers = model._resolve_providers()
    opts = providers[0][1]
    assert opts["gpu_mem_limit"] == 12 * 1024 * 1024 * 1024


def test_cpu_profile_has_no_cuda_opts(fake_ml_modules, monkeypatch):
    """USE_GPU=false -> reine CPU-Provider, keine CUDA-Optionen."""
    _clear_env(monkeypatch)
    monkeypatch.setenv("POLYSCHNACK_USE_GPU", "false")
    _reload_config(monkeypatch)

    from polyschnack_service import model
    importlib.reload(model)
    model._CUDA_PRELOADED = False

    providers = model._resolve_providers()
    names = [p if isinstance(p, str) else p[0] for p in providers]
    assert "CUDAExecutionProvider" not in names
    assert "CPUExecutionProvider" in names
