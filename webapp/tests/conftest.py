"""pytest configuration for webapp tests.

Adds the project root so tests can do 'from app.asr_client import _parse_result'.
"""
from __future__ import annotations

import sys
from pathlib import Path

_project_root = str(Path(__file__).resolve().parent.parent)  # webapp/
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)
