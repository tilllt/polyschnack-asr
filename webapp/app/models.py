"""SQLModel table definitions for the PoC UI.

A single ``Recording`` model represents one uploaded audio file together with
its transcription state and results.  The ``segments`` column stores the
word/sentence-level timeline returned by the ASR service as a JSON list.
"""
from __future__ import annotations

import datetime as dt
import uuid
from typing import Any, List, Optional

from sqlalchemy import JSON, Column
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
    status: str = "uploaded"  # uploaded | processing | done | failed
    text: Optional[str] = None
    #: JSON list of {start, end, text} dicts; stored as SQLite JSON column.
    segments: Optional[List[Any]] = Field(default=None, sa_column=Column(JSON))
    error: Optional[str] = None
    processing_ms: Optional[float] = None

    # --- progress (0-100, updated during processing) ---
    progress_pct: int = 0

    # --- timestamps ---
    created_at: dt.datetime = Field(
        default_factory=lambda: dt.datetime.now(dt.timezone.utc)
    )

    # --- post-processing flags ---
    #: User opted into VAD silence trimming for this recording.
    enable_vad: bool = False
    #: User opted into speaker diarization for this recording.
    enable_diarize: bool = False
    #: User opted into live streaming preview (SSE per-chunk results).
    enable_streaming: bool = False

    # --- preprocessing flags ---
    enable_noise_reduce: bool = True

    # --- content hash (for duplicate detection) ---
    content_hash: Optional[str] = Field(default=None, index=True)

    # --- user (optional) ---
    user_id: Optional[int] = Field(default=None, foreign_key="user.id", index=True)

    # --- WhatsApp / batch metadata ---
    #: Opaque identifier grouping files uploaded together.
    batch_id: Optional[str] = None
    #: Timestamp parsed from a WhatsApp filename; None if not a WhatsApp file.
    recorded_at: Optional[dt.datetime] = None
    #: "whatsapp" if the filename matched the WhatsApp pattern, else None.
    source: Optional[str] = None


class User(SQLModel, table=True):
    """OIDC-authenticated user — linked to recordings via user_id."""
    id: Optional[int] = Field(default=None, primary_key=True)
    sub: str = Field(unique=True, index=True)
    preferred_username: Optional[str] = None
    email: Optional[str] = None
    name: Optional[str] = None
    created_at: dt.datetime = Field(
        default_factory=lambda: dt.datetime.now(dt.timezone.utc)
    )
