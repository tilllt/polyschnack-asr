"""VRAM-Prognose: _check_long_audio schlägt VOR dem Enqueue fehl.

Regression 2026-08-14: eine zu lange Datei fürs Backend führte erst NACH dem
CUDA-OOM zu einer Fehlermeldung. Seit dem Fix: 409 mit klarem Hinweis
(Live-Modus aktivieren / anderes Backend) BEVOR der Job startet.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import app.routers.recordings as recordings_mod
from app.routers.recordings import _check_long_audio


def _rec(duration_s: float, stored_path: str = "/tmp/x.wav"):
    return SimpleNamespace(duration_s=duration_s, stored_path=stored_path)


def _patch_registry(monkeypatch, long_audio: dict | None):
    import app.service_registry as reg

    monkeypatch.setattr(
        reg, "get_service",
        lambda name: {"long_audio": long_audio} if long_audio else {},
    )


def test_keine_grenze_kein_block(monkeypatch):
    _patch_registry(monkeypatch, None)
    _check_long_audio("ps-pk-onnx", _rec(99999))  # darf nicht werfen


def test_unter_grenze_kein_block(monkeypatch):
    _patch_registry(monkeypatch, {"max_safe_duration_s": 7200, "streaming_advice": False})
    _check_long_audio("crispr-ark", _rec(3600))


def test_ueber_grenze_streaming_hinweis(monkeypatch):
    _patch_registry(monkeypatch, {"max_safe_duration_s": 3600, "streaming_advice": True})
    with pytest.raises(HTTPException) as ei:
        _check_long_audio("ps-pk-onnx", _rec(150 * 60))
    assert ei.value.status_code == 409
    msg = ei.value.detail
    assert "150 min" in msg
    assert "Live-Modus" in msg
    assert "60 min" in msg


def test_ueber_grenze_ohne_streaming(monkeypatch):
    _patch_registry(monkeypatch, {"max_safe_duration_s": 3600, "streaming_advice": False})
    with pytest.raises(HTTPException) as ei:
        _check_long_audio("crispr-ark", _rec(150 * 60))
    msg = ei.value.detail
    assert "keinen Live-Modus" in msg
    assert "ps-pk-onnx" in msg  # verweist aufs Default-Backend


def test_alt_recording_echte_dauer_unter_grenze(monkeypatch, tmp_path):
    """Alt-Datensätze haben eine grobe Schätz-Dauer (oft 2× zu hoch) — wenn
    die ECHTE Dauer (ffprobe) unter der Grenze liegt, wird NICHT blockiert."""
    f = tmp_path / "a.mp3"
    f.write_bytes(b"mp3")
    _patch_registry(monkeypatch, {"max_safe_duration_s": 7200, "streaming_advice": False})
    # rec.duration_s = Schätzwert 300 min; ffprobe sagt 30 min → ok
    monkeypatch.setattr(recordings_mod, "probe_duration_s", lambda b, fallback_estimate=0: 1800.0)
    _check_long_audio("crispr-ark", _rec(18000, stored_path=str(f)))


# --- dynamische VRAM-Grenze (long_audio.auto_vram) -------------------------

def test_auto_vram_grenze_aus_freiem_vram(monkeypatch):
    """auto_vram: Grenze = (free - safety) / vram_per_minute. 8 GB free,
    safety 2, 0.1 GB/min → 3600 s → 59 min ok, 61 min blockiert."""
    _patch_registry(monkeypatch, {"auto_vram": True, "vram_per_minute_gb": 0.1,
                                  "vram_safety_gb": 2, "max_safe_duration_s": 7200,
                                  "streaming_advice": False})
    monkeypatch.setattr(recordings_mod, "_probe_host_vram_gb", lambda: 8.0)
    _check_long_audio("crispr-ark", _rec(59 * 60))
    with pytest.raises(HTTPException):
        _check_long_audio("crispr-ark", _rec(61 * 60))


def test_auto_vram_ohne_messwert_fallback_statisch(monkeypatch):
    """Kein VRAM-Messwert (CPU-only / Backend down) → statische Grenze."""
    _patch_registry(monkeypatch, {"auto_vram": True, "vram_per_minute_gb": 0.1,
                                  "vram_safety_gb": 2, "max_safe_duration_s": 7200,
                                  "streaming_advice": False})
    monkeypatch.setattr(recordings_mod, "_probe_host_vram_gb", lambda: None)
    _check_long_audio("crispr-ark", _rec(2 * 3600))  # 2 h == Grenze → ok


def test_auto_vram_cap_als_obergrenze(monkeypatch):
    """Dynamische Grenze darf den statischen Cap nie überschreiten —
    24 GB free, 0.01 GB/min → 132 000 s, aber Cap 7200 s greift."""
    _patch_registry(monkeypatch, {"auto_vram": True, "vram_per_minute_gb": 0.01,
                                  "vram_safety_gb": 2, "max_safe_duration_s": 7200,
                                  "streaming_advice": False})
    monkeypatch.setattr(recordings_mod, "_probe_host_vram_gb", lambda: 24.0)
    _check_long_audio("crispr-ark", _rec(2 * 3600))          # exakt am Cap → ok
    with pytest.raises(HTTPException):
        _check_long_audio("crispr-ark", _rec(2 * 3600 + 60))  # Cap + 1 min → 409
