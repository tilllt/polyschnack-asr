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

    #: OIDC (optional — when unset, no auth)
    OIDC_CLIENT_ID: str = os.getenv("OIDC_CLIENT_ID", "")
    OIDC_CLIENT_SECRET: str = os.getenv("OIDC_CLIENT_SECRET", "")
    OIDC_ISSUER: str = os.getenv("OIDC_ISSUER", "")
    OIDC_SCOPE: str = os.getenv("OIDC_SCOPE", "openid profile email")
    SESSION_SECRET: str = os.getenv("SESSION_SECRET", "")
    BASE_URL: str = os.getenv("BASE_URL", "http://localhost:8088").rstrip("/")

    #: Public-space retention in minutes; 0 = off
    PUBLIC_RETENTION_MINUTES: int = int(os.getenv("PUBLIC_RETENTION_MINUTES", "60"))

    #: Max upload file size in MB (default 1024 = 1 GB)
    MAX_UPLOAD_SIZE_MB: int = int(os.getenv("MAX_UPLOAD_SIZE_MB", "1024"))

    #: Comma-separated sub|email list of admin users (admin area).
    POLYSCHNACK_ADMINS: str = os.getenv("POLYSCHNACK_ADMINS", "")
    #: Comma-separated OIDC group names that grant admin rights.
    POLYSCHNACK_ADMIN_GROUPS: str = os.getenv("POLYSCHNACK_ADMIN_GROUPS", "")


    #: Which ASR backend adapter to use: ``pk-python`` or ``pk-cpp``
    ASR_BACKEND: str = os.getenv("ASR_BACKEND", "pk-python")


settings = _Settings()

# Derived: OIDC is enabled when all required fields are set
settings.OIDC_ENABLED = bool(
    settings.OIDC_CLIENT_ID and settings.OIDC_CLIENT_SECRET and settings.OIDC_ISSUER
)
