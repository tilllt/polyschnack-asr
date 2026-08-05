"""Persisted admin overrides — one JSON file in DATA_DIR (ponytail: no DB table).

Only the default-backend override lives here (Task 8, Decision 8). Concurrency
is derived from endpoint capacities and is NOT configurable (Decision 3).
"""
from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any, Optional

from .config import settings

_lock = threading.Lock()


def _path() -> Path:
    return Path(settings.DATA_DIR) / "config.json"


def get(key: str, default: Any = None) -> Any:
    with _lock:
        try:
            data = json.loads(_path().read_text())
            return data.get(key, default)
        except (OSError, json.JSONDecodeError):
            return default


def set(key: str, value: Any) -> None:
    with _lock:
        p = _path()
        p.parent.mkdir(parents=True, exist_ok=True)
        data = {}
        try:
            data = json.loads(p.read_text())
        except (OSError, json.JSONDecodeError):
            pass
        data[key] = value
        p.write_text(json.dumps(data, indent=2))


def delete(key: str) -> None:
    with _lock:
        p = _path()
        try:
            data = json.loads(p.read_text())
        except (OSError, json.JSONDecodeError):
            return
        data.pop(key, None)
        p.write_text(json.dumps(data, indent=2))


def effective_backend() -> Optional[str]:
    """Override or env default (None = env default in force)."""
    value = get("default_backend") or None
    if value is None:
        return None
    # Backend-ID-Umbau (2026-08): alte Adapter-IDs aus config.json mappen.
    return {
        "pk-python": "ps-pk-onnx",
        "pk-cpp": "crispr-pk-cpp",
        "qwen3-asr": "crispr-qwen3",
        "ark-asr": "crispr-ark",
        "moonshine-de": "crispr-moonshine-de",
        "canary-asr": "crispr-canary",
        "voxtral": "ps-voxtral",
    }.get(value, value)
