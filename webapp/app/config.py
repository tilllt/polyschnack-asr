"""Application settings loaded from environment variables.

Import ``settings`` to access typed configuration across all modules.
All values are resolved once at import time — no side effects.
"""
from __future__ import annotations

import os
import secrets
from pathlib import Path


def _load_or_create_session_secret(data_dir: Path) -> str:
    """Persistierter SESSION_SECRET (Review 2026-08-15, P1.4/P1.5).

    Ohne Env-Var wurde bisher (a) crypto.py auf sha256('dev') zurückfallen —
    ein öffentlich bekannter Schlüssel für BYOK-Credentials — und (b) main.py
    pro Prozess ein ZUFÄLLIGER Key erzeugen, wodurch jeder Restart alle
    anon-User von ihren Aufnahmen trennte. Ab jetzt: einmal erzeugen, in
    DATA_DIR/.session_secret ablegen, dauerhaft wiederverwenden.
    """
    env = os.getenv("SESSION_SECRET", "").strip()
    if env:
        return env
    try:
        data_dir.mkdir(parents=True, exist_ok=True)
        secret_file = data_dir / ".session_secret"
        if secret_file.exists():
            val = secret_file.read_text().strip()
            if val:
                return val
        val = secrets.token_urlsafe(48)
        secret_file.write_text(val)
        try:
            os.chmod(secret_file, 0o600)
        except OSError:
            pass
        return val
    except OSError:
        # DATA_DIR nicht beschreibbar (z.B. read-only Tests) — dann lieber
        # hart abbrechen als mit 'dev' zu signieren (s. crypto.py Guard).
        raise RuntimeError(
            "SESSION_SECRET ist nicht gesetzt und DATA_DIR ist nicht "
            "beschreibbar — bitte SESSION_SECRET als Env-Var setzen."
        )


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

    #: Shared-Key-Auth für Benchmark-Self-Service (Change 031): kommaseparierte
    #: Keys für GET /package, /package/sha256 und POST /submit. Leer = Endpunkte
    #: deaktiviert (503). Runner (vast.ai) nutzt denselben Wert als
    #: BENCHMARK_API_KEY.
    BENCHMARK_API_KEYS: str = os.getenv("BENCHMARK_API_KEYS", "")

    #: Base URL of the ASR inference service (no trailing slash).
    #: Env-Var = Backend-ID (Option C): PS_PK_ONNX_URL.
    ASR_URL: str = os.getenv("PS_PK_ONNX_URL", "http://ps-pk-onnx:5092").rstrip("/")

    #: Model name forwarded in every transcription request.
    ASR_MODEL: str = os.getenv("ASR_MODEL", "parakeet-tdt-0.6b-v3")

    # Diarization-Service (CrispASR-Server, eigener Container — Option B).
    # Kein pyannote/torch mehr in der Webapp; der diar-Container liefert
    # diarized_json mit Speaker-Labels A/B/C… (Container-Port 5098)
    # Env-Var = Backend-ID (Option C): CRISPR_DIAR_URL.
    DIAR_URL: str = os.getenv("CRISPR_DIAR_URL", "http://crispr-diar:5098").rstrip("/")

    #: Diarization-Methode im CrispASR-Server (pyannote|foxnose|energy|…).
    DIARIZE_METHOD: str = os.getenv("DIARIZE_METHOD", "pyannote")

    #: Chunk-Sekunden für den diar-Server (parakeet Longform-Fix 2026-08-15):
    #: Ohne explizites Chunking bricht CrispASR lange Audios nach ~165 s ab
    #: (Memory-Cap, CrispASR-Issue #257). 30 s ist der Server-Default.
    DIARIZE_CHUNK_SECONDS: int = int(os.getenv("DIARIZE_CHUNK_SECONDS", "30"))

    #: OIDC (optional — when unset, no auth)
    OIDC_CLIENT_ID: str = os.getenv("OIDC_CLIENT_ID", "")
    OIDC_CLIENT_SECRET: str = os.getenv("OIDC_CLIENT_SECRET", "")
    OIDC_ISSUER: str = os.getenv("OIDC_ISSUER", "")
    OIDC_SCOPE: str = os.getenv("OIDC_SCOPE", "openid profile email")
    #: Review 2026-08-15 (P1.4/P1.5): persistiert statt 'dev' oder Zufall pro
    #: Prozess — siehe _load_or_create_session_secret.
    SESSION_SECRET: str = _load_or_create_session_secret(Path(os.getenv("DATA_DIR", "/data")))
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

    #: Change 043 — YouTube-Import-Tor-Fallback (letzte Download-Kaskaden-
    #: Stufe bei Bot-Erkennung). Default AUS; Admin schaltet pro Installation
    #: an (User-Entscheidung 2026-08-20).
    POLYSCHNACK_TOR_FALLBACK: bool = os.getenv("POLYSCHNACK_TOR_FALLBACK", "").lower() in ("1", "true", "yes", "on")
    #: Max. Circuit-Versuche (jeder Versuch = neuer Tor-Exit nach restart).
    POLYSCHNACK_TOR_MAX_CIRCUITS: int = int(os.getenv("POLYSCHNACK_TOR_MAX_CIRCUITS", "5"))
    #: Max. Audio-Größe in MB für Tor-Downloads (yt-dlp --max-filesize).
    POLYSCHNACK_TOR_MAX_SIZE_MB: int = int(os.getenv("POLYSCHNACK_TOR_MAX_SIZE_MB", "500"))
    #: Rate-Limit: max. Tor-Downloads pro User pro Stunde (rolling window).
    POLYSCHNACK_TOR_MAX_PER_HOUR: int = int(os.getenv("POLYSCHNACK_TOR_MAX_PER_HOUR", "2"))
    #: Leerlauf-Minuten nach dem letzten Tor-Download, dann stoppt die Webapp
    #: den ps-tor-Container wieder (on-demand, kein Dauerbetrieb).
    POLYSCHNACK_TOR_IDLE_MINUTES: int = int(os.getenv("POLYSCHNACK_TOR_IDLE_MINUTES", "30"))

    #: Default ASR backend for new jobs (Task 6; concurrency is derived, not configured).
    POLYSCHNACK_DEFAULT_BACKEND: str = os.getenv("POLYSCHNACK_DEFAULT_BACKEND", "ps-pk-onnx")

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


    #: Which ASR backend adapter to use: ``ps-pk-onnx`` or ``crispr-pk-cpp``
    ASR_BACKEND: str = os.getenv("ASR_BACKEND", "ps-pk-onnx")


settings = _Settings()

# Derived: OIDC is enabled when all required fields are set
settings.OIDC_ENABLED = bool(
    settings.OIDC_CLIENT_ID and settings.OIDC_CLIENT_SECRET and settings.OIDC_ISSUER
)
