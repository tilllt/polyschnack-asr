"""pytest configuration for webapp tests.

Adds the app directory to sys.path so imports like 'from asr_client import _parse_result'
work (replacing the relative 'from .config' with 'from config').
"""
from __future__ import annotations

import sys
from pathlib import Path

# Add the app directory so tests can do "from asr_client import _parse_result"
_app_dir = str(Path(__file__).resolve().parent.parent / "app")
if _app_dir not in sys.path:
    sys.path.insert(0, _app_dir)
