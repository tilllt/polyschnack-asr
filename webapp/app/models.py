"""SQLModel table definitions for the PoC UI.

A single ``Recording`` model represents one uploaded audio file together with
its transcription state and results.  The ``segments`` column stores the
word/sentence-level timeline returned by the ASR service as a JSON list.
"""
from __future__ import annotations

import datetime as dt
import uuid
from typing import Any, List, Optional

from sqlalchemy import JSON, Column, UniqueConstraint
from sqlmodel import Field, SQLModel


class Recording(SQLModel, table=True):
    """Persisted metadata + transcription result for one uploaded audio file."""

    id: Optional[int] = Field(default=None, primary_key=True)

    # Unique external reference (UUID hex) — prevents browser-cache confusion
    # when recordings are deleted and re-created.
    uid: str = Field(
        default_factory=lambda: uuid.uuid4().hex,
        unique=True,
        index=True,
    )

    # --- upload metadata ---
    original_name: str
    stored_path: str
    mime: str = "application/octet-stream"
    size_bytes: int = 0

    # --- transcription results ---
    duration_s: Optional[float] = None
    language: Optional[str] = None
    status: str = "uploaded"  # uploaded | queued | processing | done | failed
    text: Optional[str] = None
    #: ASR endpoint this recording is transcribed with (queue binding, Task 6).
    backend: str = "ps-pk-onnx"
    #: JSON list of {start, end, text} dicts; stored as SQLite JSON column.
    segments: Optional[List[Any]] = Field(default=None, sa_column=Column(JSON))
    error: Optional[str] = None
    processing_ms: Optional[float] = None

    # --- progress (0-100, updated during processing) ---
    progress_pct: int = 0
    #: Phasen-Hinweis während der Verarbeitung ("diarization", …) — null wenn ASR
    progress_note: Optional[str] = None

    # --- timestamps ---
    created_at: dt.datetime = Field(
        default_factory=lambda: dt.datetime.now(dt.timezone.utc)
    )
    #: Letztes Update (Progress/Status) — Basis für den Stale-Processing-
    #: Watchdog: Recordings, deren Verarbeitung hängt/gekillt wurde (z.B.
    #: Container-OOM), bleiben bei status="processing" und frischem updated_at
    #: stehen → Sweep markiert sie nach Ablauf der Grenze als failed.
    updated_at: dt.datetime = Field(
        default_factory=lambda: dt.datetime.now(dt.timezone.utc)
    )

    # --- post-processing flags ---
    #: User opted into VAD silence trimming for this recording.
    enable_vad: bool = False
    #: User opted into speaker diarization for this recording.
    enable_diarize: bool = False
    #: Diarization-Tuning: bekannte Sprecherzahl (min=max), None = auto.
    diarize_num_speakers: Optional[int] = Field(default=None)
    #: Diarization-Tuning: min. Pause zwischen Sprecherwechseln (Sek.),
    #: None = Pipeline-Default. Höher = weniger Wechsel.
    diarize_min_duration_off: Optional[float] = Field(default=None)
    #: Diarization-Methode pro Recording (pyannote|foxnose|energy|xcorr|vad-turns),
    #: None = Server-Default aus DIARIZE_METHOD.
    diarize_method: Optional[str] = Field(default=None)
    #: User opted into live streaming preview (SSE per-chunk results).
    enable_streaming: bool = False

    # --- waveform peaks (cached for fast WaveSurfer render) ---
    waveform_peaks: Optional[List[float]] = Field(default=None, sa_column=Column(JSON))

    # --- Playback-Preview (schlanke Sidecar für WaveSurfer, 2026-08-15) ---
    # Komprimierte 64-kbps-MP3 (16 kHz mono) NEBEN dem Original: der
    # Browser-Player lädt NUR diese kleine Datei fürs Playback; die
    # Transkription läuft weiter mit dem vollen Audio (stored_path).
    # Wiedereinführung der Pipeline, die 665ba08 entfernte (MediaElement-
    # Experiment brach → WebAudio braucht kleine Datei statt Voll-Decode).
    preview_path: Optional[str] = Field(default=None)
    preview_size_bytes: Optional[int] = Field(default=None)

    # --- notification URLs ---
    notification_urls: Optional[str] = Field(default=None)

    # --- preprocessing flags ---
    enable_noise_reduce: bool = True
    #: ffmpeg pre-processing level — "off", "light", "medium", "aggressive".
    enable_enhance: str = "off"

    # --- opt-in processing (Task A12/A13): nichts läuft automatisch ---
    #: Interpunktion nach der Transkription (Modus via POLYSCHNACK_PUNCTUATION_MODE).
    enable_punctuation: bool = False
    #: LLM-Optimierung nach der Transkription (kostenpflichtig → nur OIDC).
    enable_llm_enhance: bool = False

    # --- Post-Processing & Delivery (Teil D) ---
    prompt_template_id: Optional[int] = Field(default=None, foreign_key="prompttemplate.id")
    delivery_target_id: Optional[int] = Field(default=None, foreign_key="deliverytarget.id")
    delivery_status: Optional[str] = None          # pending | done | failed
    delivery_error: Optional[str] = None
    # --- BYOK (Teil E): eigener LLM-Endpunkt des Users ---
    llm_endpoint_id: Optional[int] = Field(default=None, foreign_key="userllmendpoint.id")

    # --- content hash (for duplicate detection) ---
    content_hash: Optional[str] = Field(default=None, index=True)

    # --- user (optional) ---
    user_id: Optional[int] = Field(default=None, foreign_key="user.id", index=True)

    # --- anonymous share link (read-only, 32-char uid = token) ---
    #: True → jeder mit dem UID-Link kann lesen (kein Login, NIE write/full).
    share_token: bool = False
    #: Zeitpunkt der Link-Erstellung — Versionen davor sind für Anon unsichtbar.
    shared_at: Optional[dt.datetime] = None

    # --- WhatsApp / batch metadata ---
    #: Opaque identifier grouping files uploaded together.
    batch_id: Optional[str] = None
    #: Timestamp parsed from a WhatsApp filename; None if not a WhatsApp file.
    recorded_at: Optional[dt.datetime] = None
    #: "whatsapp" if the filename matched the WhatsApp pattern, else None.
    source: Optional[str] = None


class User(SQLModel, table=True):
    """User — OIDC-authentifiziert (kind="oidc") oder anonyme Session (kind="anonymous").

    Anonyme User (Task B1): Identität per Session-Cookie, zufälliger Anzeigename,
    last_seen_at für die Retention-Löschung (Default 15 min nach letzter Aktivität).
    """
    id: Optional[int] = Field(default=None, primary_key=True)
    sub: str = Field(unique=True, index=True)
    kind: str = "oidc"  # oidc | anonymous
    display_name: Optional[str] = None
    last_seen_at: Optional[dt.datetime] = None
    preferred_username: Optional[str] = None
    email: Optional[str] = None
    name: Optional[str] = None
    created_at: dt.datetime = Field(
        default_factory=lambda: dt.datetime.now(dt.timezone.utc)
    )


class RecordingShare(SQLModel, table=True):
    """Gewährt einem User Zugriff auf ein fremdes Recording (read|write|full)."""
    id: Optional[int] = Field(default=None, primary_key=True)
    rec_id: int = Field(foreign_key="recording.id", index=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    level: str = "read"  # read | write | full
    created_at: dt.datetime = Field(
        default_factory=lambda: dt.datetime.now(dt.timezone.utc)
    )
    __table_args__ = (UniqueConstraint("rec_id", "user_id"),)


class TranscriptVersion(SQLModel, table=True):
    """Voll-Snapshot einer Transkription (text + segments) je Änderung.

    kind ∈ {transcribe, retranscribe, edit, restore, postprocess}.
    """
    id: Optional[int] = Field(default=None, primary_key=True)
    rec_id: int = Field(foreign_key="recording.id", index=True)
    version_no: int = 0
    kind: str = "transcribe"
    text: Optional[str] = None
    segments: Optional[List[Any]] = Field(default=None, sa_column=Column(JSON))
    backend: str = ""
    language: Optional[str] = None
    created_at: dt.datetime = Field(
        default_factory=lambda: dt.datetime.now(dt.timezone.utc)
    )
    created_by_user_id: Optional[int] = None


class ApiKey(SQLModel, table=True):
    """API-Key für externe Anwendungen (Teil C) — wie ein Share mit Rechte-Deckel.

    Der Klartext-Token wird genau einmal angezeigt; in der DB liegt nur der
    SHA-256-Hash. ``level`` ∈ read|write|full (gleiche Ebenen wie Shares).
    """
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    name: str = "default"
    level: str = "read"
    token_hash: str = Field(index=True, unique=True)
    created_at: dt.datetime = Field(
        default_factory=lambda: dt.datetime.now(dt.timezone.utc)
    )
    last_used_at: Optional[dt.datetime] = None


def hash_token(token: str) -> str:
    import hashlib

    return hashlib.sha256(token.encode()).hexdigest()


class PromptTemplate(SQLModel, table=True):
    """Per-User Prompt-Template für LLM-Post-Processing (Teil D)."""
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    name: str = "default"
    prompt: str = ""
    created_at: dt.datetime = Field(default_factory=lambda: dt.datetime.now(dt.timezone.utc))


class UserLlmEndpoint(SQLModel, table=True):
    """BYOK (Teil E) — eigener OpenAI-kompatibler LLM-Endpunkt eines Users.

    api_key wird per Fernet verschlüsselt gespeichert (crypto.encrypt) und
    nie in API-Antworten/Logs ausgegeben.
    """
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    name: str = "default"
    base_url: str = ""            # z. B. https://api.mistral.ai/v1
    api_key: str = ""             # Fernet-verschlüsselt
    model: str = "deepseek-chat"
    created_at: dt.datetime = Field(default_factory=lambda: dt.datetime.now(dt.timezone.utc))


class DeliveryTarget(SQLModel, table=True):
    """Ziel für die fertige Transkription (Task D3): email | webdav.

    ``config`` ist JSON; Passwörter darin sind per Fernet verschlüsselt
    (siehe ``crypto.py``) — nie im Klartext in der DB.
    """
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    name: str = "default"
    kind: str = "email"  # email | webdav
    config: Optional[str] = None  # JSON-String (Creds verschlüsselt)
    created_at: dt.datetime = Field(
        default_factory=lambda: dt.datetime.now(dt.timezone.utc)
    )
