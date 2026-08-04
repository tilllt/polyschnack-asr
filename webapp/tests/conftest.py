"""pytest configuration for webapp tests.

Adds the project root so tests can do 'from app.asr_client import _parse_result'.
Also redirects DATA_DIR to a writable temp location BEFORE the app is imported
(app/routers/models.py mkdirs DATA_DIR/models at import time — fails on /data
when running as non-root).
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

_project_root = str(Path(__file__).resolve().parent.parent)  # webapp/
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

_tmp_data = tempfile.mkdtemp(prefix="webapp_test_data_")
os.environ.setdefault("DATA_DIR", _tmp_data)
os.environ.setdefault("AUDIO_DIR", str(Path(_tmp_data) / "audio"))
