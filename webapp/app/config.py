"""Application settings loaded from environment variables.

Import ``settings`` to access typed configuration across all modules.
All values are resolved once at import time — no side effects.
"""
from __future__ import annotations

import os
from pathlib import Path


class _Settings:
    """Typed container for environment-driven configuration."""

    #: Base data directory (docker volume mount point).
    DATA_DIR: Path = Path(os.getenv("DATA_DIR", "/data"))

    #: Directory where audio files are stored on disk.
    AUDIO_DIR: Path = Path(os.getenv("AUDIO_DIR", str(Path(os.getenv("DATA_DIR", "/data")) / "audio")))

    #: Path to the SQLite database file.
    DB_PATH: Path = Path(os.getenv("DB_PATH", str(Path(os.getenv("DATA_DIR", "/data")) / "app.db")))

    #: Base URL of the ASR inference service (no trailing slash).
    ASR_URL: str = os.getenv("ASR_URL", "http://asr:5092").rstrip("/")

    #: Model name forwarded in every transcription request.
    ASR_MODEL: str = os.getenv("ASR_MODEL", "parakeet-tdt-0.6b-v3")


settings = _Settings()
