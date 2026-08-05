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

    #: Benchmark-Daten (versionierte Manifeste + Audio) — gemountetes Volume.
    BENCHMARK_DATA_DIR: Path = Path(os.getenv("BENCHMARK_DATA_DIR", str(Path(os.getenv("DATA_DIR", "/data")) / "benchmark")))

    #: Base URL of the ASR inference service (no trailing slash).
    ASR_URL: str = os.getenv("ASR_URL", "http://asr:5092").rstrip("/")

    #: Model name forwarded in every transcription request.
    ASR_MODEL: str = os.getenv("ASR_MODEL", "parakeet-tdt-0.6b-v3")

    # Diarization-Service (CrispASR-Server, eigener Container — Option B).
    # Kein pyannote/torch mehr in der Webapp; der diar-Container liefert
    # diarized_json mit Speaker-Labels A/B/C… (Container-Port 5096)
    DIAR_URL: str = os.getenv("DIAR_URL", "http://diar:5096").rstrip("/")

    #: Diarization-Methode im CrispASR-Server (pyannote|foxnose|energy|…).
    DIARIZE_METHOD: str = os.getenv("DIARIZE_METHOD", "pyannote")

    #: OIDC (optional — when unset, no auth)
    OIDC_CLIENT_ID: str = os.getenv("OIDC_CLIENT_ID", "")
    OIDC_CLIENT_SECRET: str = os.getenv("OIDC_CLIENT_SECRET", "")
    OIDC_ISSUER: str = os.getenv("OIDC_ISSUER", "")
    OIDC_SCOPE: str = os.getenv("OIDC_SCOPE", "openid profile email")
    SESSION_SECRET: str = os.getenv("SESSION_SECRET", "")
    BASE_URL: str = os.getenv("BASE_URL", "http://localhost:8088").rstrip("/")

    #: Public-space retention in minutes; 0 = off
    PUBLIC_RETENTION_MINUTES: int = int(os.getenv("PUBLIC_RETENTION_MINUTES", "60"))

    #: Retention für anonyme Sessions (Task B1): 15 min nach der letzten Aktivität.
    POLYSCHNACK_ANON_RETENTION_MINUTES: int = int(os.getenv("POLYSCHNACK_ANON_RETENTION_MINUTES", "15"))
    #: Harte Limits für anonyme User (Task B5).
    POLYSCHNACK_ANON_MAX_DURATION_S: int = int(os.getenv("POLYSCHNACK_ANON_MAX_DURATION_S", "300"))
    POLYSCHNACK_ANON_MAX_DISK_MB: int = int(os.getenv("POLYSCHNACK_ANON_MAX_DISK_MB", "500"))
    POLYSCHNACK_ANON_MAX_UPLOAD_MB: int = int(os.getenv("POLYSCHNACK_ANON_MAX_UPLOAD_MB", "100"))

    #: Max upload file size in MB (default 1024 = 1 GB)
    MAX_UPLOAD_SIZE_MB: int = int(os.getenv("MAX_UPLOAD_SIZE_MB", "1024"))

    #: Comma-separated sub|email list of admin users (admin area).
    POLYSCHNACK_ADMINS: str = os.getenv("POLYSCHNACK_ADMINS", "")
    #: Comma-separated OIDC group names that grant admin rights.
    POLYSCHNACK_ADMIN_GROUPS: str = os.getenv("POLYSCHNACK_ADMIN_GROUPS", "")

    #: Base URL of the restrictive docker-socket-proxy (Task 4).
    DOCKER_PROXY_URL: str = os.getenv("DOCKER_PROXY_URL", "http://docker-proxy:2375")
    #: Optional token the proxy requires (empty = no auth header).
    DOCKER_PROXY_TOKEN: str = os.getenv("DOCKER_PROXY_TOKEN", "")

    #: Default ASR backend for new jobs (Task 6; concurrency is derived, not configured).
    POLYSCHNACK_DEFAULT_BACKEND: str = os.getenv("POLYSCHNACK_DEFAULT_BACKEND", "pk-python")

    #: Opt-in processing (Task A12/A13) — Defaults aus, nichts läuft automatisch.
    POLYSCHNACK_DEFAULT_PUNCTUATION: bool = os.getenv("POLYSCHNACK_DEFAULT_PUNCTUATION", "").lower() in ("1", "true", "yes", "on")
    #: Punctuation-Modus: off | local (offline fullstop) | llm (DeepSeek/LiteLLM, paid).
    POLYSCHNACK_PUNCTUATION_MODE: str = os.getenv("POLYSCHNACK_PUNCTUATION_MODE", "off")
    POLYSCHNACK_DEFAULT_LLM_ENHANCE: bool = os.getenv("POLYSCHNACK_DEFAULT_LLM_ENHANCE", "").lower() in ("1", "true", "yes", "on")

    #: LLM-Post-Processing (Teil D) — OpenAI-kompatibler Endpunkt, Defaults leer
    #: (URL/Key müssen per Env gesetzt werden; Model mit sinnvollem Default).
    POLYSCHNACK_LLM_URL: str = os.getenv("POLYSCHNACK_LLM_URL", "")
    POLYSCHNACK_LLM_API_KEY: str = os.getenv("POLYSCHNACK_LLM_API_KEY", "")
    POLYSCHNACK_LLM_MODEL: str = os.getenv("POLYSCHNACK_LLM_MODEL", "deepseek-chat")

    #: SMTP für Delivery-Targets (Task D5) — leer = Mail-Targets deaktiviert.
    POLYSCHNACK_SMTP_HOST: str = os.getenv("POLYSCHNACK_SMTP_HOST", "")
    POLYSCHNACK_SMTP_PORT: int = int(os.getenv("POLYSCHNACK_SMTP_PORT", "587"))
    POLYSCHNACK_SMTP_USER: str = os.getenv("POLYSCHNACK_SMTP_USER", "")
    POLYSCHNACK_SMTP_PASS: str = os.getenv("POLYSCHNACK_SMTP_PASS", "")
    POLYSCHNACK_SMTP_FROM: str = os.getenv("POLYSCHNACK_SMTP_FROM", "")
    #: Max jobs waiting in the queue (per process).
    POLYSCHNACK_MAX_QUEUE_LEN: int = int(os.getenv("POLYSCHNACK_MAX_QUEUE_LEN", "20"))
    #: Optional API key for the Voxtral endpoint (empty = no auth header).
    POLYSCHNACK_VOXTRAL_API_KEY: str = os.getenv("POLYSCHNACK_VOXTRAL_API_KEY", "")


    #: Which ASR backend adapter to use: ``pk-python`` or ``pk-cpp``
    ASR_BACKEND: str = os.getenv("ASR_BACKEND", "pk-python")


settings = _Settings()

# Derived: OIDC is enabled when all required fields are set
settings.OIDC_ENABLED = bool(
    settings.OIDC_CLIENT_ID and settings.OIDC_CLIENT_SECRET and settings.OIDC_ISSUER
)
