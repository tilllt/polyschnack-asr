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
    #: Change 014 (2026-08-18): editierbarer Anzeige-Titel; None → Fallback
    #: original_name in der Serialisierung. Quelle der Wahrheit ist die DB;
    #: ein Sidecar {stored_path}.meta.json spiegelt title/original_name.
    title: Optional[str] = Field(default=None)
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
    #: Change 009 (2026-08-17): manuelle Segment-Aufteilung aktiv (Grenz-Drag,
    #: true nach jeder Segment-Struktur-OP (Grenz-Drag, +/−, Split,
    #: Re-Segmentierung). Die Anzeige unterscheidet seit Change 088 pro
    #: Segment per `_manual`-Flag: markierte Segmente bleiben exakt,
    #: unmarkierte werden nach der gewählten Segmentlänge geteilt.
    #: false bei neuer Transkription/Retranscribe/Restore.
    segments_manual: bool = False
    error: Optional[str] = None
    processing_ms: Optional[float] = None
    #: Change 085: Phasen-Zeiten je Job (ms) — Stichproben für die
    #: selbstlernende ETA. Keys: vad, enhance:<level>, asr:<backend>,
    #: diar:<methode>, punc_truecase. Align läuft post-done im
    #: Hintergrund-Worker (Ingest separat über rtf_estimates).
    phase_times_ms: Optional[Dict[str, float]] = Field(
        default=None, sa_column=Column(JSON)
    )
    # --- Change 086: Kosten je Job (virtuelle Credits) ---
    #: Endabrechnung in Cent nach Abschluss (User sichtbar).
    cost_cents: Optional[int] = None
    #: Vorschuss beim Start (Reserve-System) — Delta wird bei Abschluss gebucht.
    reserved_cents: Optional[int] = None
    # --- Change 045: Status des präzisen (Forced-)Alignments ---
    # "done" (Default: aligniert/synchron) | "pending" (läuft im Hintergrund) |
    # "running" (Worker aktiv) | "skipped" (Aligner down / deaktiviert)
    alignment: str = "done"
    # --- Change 057: Status der Diarization (Re-Diarize) ---
    # "done" (Default: Sprecher zugeordnet) | "pending" | "running" |
    # "failed" (Diar-Dienst down/Fehler) | "skipped" (Ergebnis verworfen)
    diar_status: str = "done"

    # --- progress (0-100, updated during processing) ---
    progress_pct: int = 0
    #: Phasen-Hinweis während der Verarbeitung ("diarization", …) — null wenn ASR
    progress_note: Optional[str] = None
    # --- Change 011 (2026-08-17): Aktivitäts-/Phasen-Zeitstempel ---
    #: Beginn der aktuellen Phase — gesetzt, wenn sich progress_note ändert.
    #: Basis für „Phase läuft seit Xs" (Frontend-ETA-Fallback).
    phase_started_at: Optional[dt.datetime] = Field(default=None)
    #: Letzter Aktivitäts-Nachweis — jeder set_progress-Aufruf aktualisiert
    #: ihn; in stillen Phasen (Sync-ASR, Diarization) tickt ein Heartbeat-
    #: Thread. Die UI unterscheidet damit „läuft, kein messbarer Fortschritt"
    #: (frischer Heartbeat) von „eingefroren/hängend" (alter Heartbeat).
    last_heartbeat_at: Optional[dt.datetime] = Field(default=None)

    #: Job-Beginn der Verarbeitung (Change 082) — Basis für ETA-Rest und
    #: „verarbeitet seit Xs". Wird in set_processing gesetzt (Auto-Migrate).
    processing_started_at: Optional[dt.datetime] = Field(default=None)

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

    # --- Settings (Change 099): leben NICHT mehr hier ---
    #: Die Transkriptions-Einstellungen (VAD, Diarize, Streaming, Enhance,
    #: Punctuation, LLM, Template/Endpoint/Delivery-Ziel) liegen versioniert
    #: im TranscriptionRun-Snapshot (siehe current_run_id). Die alten
    #: Spalten wurden per Migration entfernt (Change 099); Leser nutzen den
    #: aktuellen Run als Quelle der Wahrheit.

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

    # --- Change 054: freie Tags zur Gruppierung/Filtrierung ---
    # JSON-Liste von Strings (z. B. ["walzen", "schellack", "review", "fertig"]);
    # leer = keine Tags. Gesetzt per PATCH /api/recordings/{uid}/tags
    # (write-Zugriff). Sortierung/Filterung der Liste nutzt die Spalte.
    tags: List[str] = Field(default_factory=list, sa_column=Column(JSON))

    # --- Post-Processing & Delivery (Teil D) ---
    #: Ziel-/Template-/Endpoint-Wahl (delivery_target_id, prompt_template_id,
    #: llm_endpoint_id) liegt versioniert im TranscriptionRun (Change 099);
    #: hier steht nur der Zustell-Status des aktuellen Ergebnisses.
    delivery_status: Optional[str] = None          # pending | done | failed
    delivery_error: Optional[str] = None

    # --- content hash (for duplicate detection) ---
    content_hash: Optional[str] = Field(default=None, index=True)

    # --- user (optional) ---
    user_id: Optional[int] = Field(default=None, foreign_key="user.id", index=True)
    #: Change 014 (2026-08-18): Eigentümer-Fallback für Legacy-public
    #: Recordings (user_id=None). Wird beim Upload (anon-Session) und beim
    #: Recovery-Restore gesetzt; ermöglicht DELETE/Re-Transcribe, obwohl
    #: permissions.py für user_id=None nur "read" vergibt. None = nur Admin.
    owner_user_id: Optional[int] = Field(default=None, foreign_key="user.id", index=True)

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

    # --- Change 094/099 (runs → results): Zeiger auf den aktuellen
    # Transkriptionslauf + sein Ergebnis. Die Settings-/Ergebnis-Spalten
    # sind seit Change 099 per Migration entfernt — Quelle der Wahrheit
    # für Settings ist der Run (siehe _run_settings-Helfer).
    current_run_id: Optional[int] = Field(default=None, foreign_key="transcriptionrun.id")
    current_result_id: Optional[int] = Field(default=None, foreign_key="transcriptionresult.id")


class TranscriptionRun(SQLModel, table=True):
    """Ein Transkriptionslauf (Change 094): Settings-Snapshot + Status.

    Jeder transcribe/re-transcribe legt einen Run an — die Antwort auf
    „welche Version entstand mit welchen Einstellungen?" lebt HIER, nicht
    im Recording. Status: queued | processing | done | failed.
    """

    id: Optional[int] = Field(default=None, primary_key=True)
    rec_id: int = Field(foreign_key="recording.id", index=True)

    # --- Settings-Snapshot (Kopie des Recording-Zustands bei Job-Start) ---
    backend: str = ""
    language: Optional[str] = None
    enable_vad: bool = False
    vad_mode: str = "off"  # Change 114: off|edges|all (User-konfigurierbar, ohne Env); enable_vad bleibt Legacy
    enable_diarize: bool = False
    diarize_num_speakers: Optional[int] = Field(default=None)
    diarize_min_duration_off: Optional[float] = Field(default=None)
    diarize_method: Optional[str] = Field(default=None)
    enable_streaming: bool = False
    enable_noise_reduce: bool = True
    enable_enhance: str = "off"
    separate_backend: str = "none"  # Change 106: none|htdemucs|mel-band-roformer (Source Separation als ASR-Vorstufe)
    enable_punctuation: bool = False
    enable_llm_enhance: bool = False
    llm_endpoint_id: Optional[int] = Field(default=None, foreign_key="userllmendpoint.id")
    prompt_template_id: Optional[int] = Field(default=None, foreign_key="prompttemplate.id")
    delivery_target_id: Optional[int] = Field(default=None, foreign_key="deliverytarget.id")

    # --- Betrieb ---
    status: str = "queued"  # queued | processing | done | failed
    progress_pct: Optional[float] = Field(default=None)
    phase: Optional[str] = Field(default=None)
    error: Optional[str] = Field(default=None)
    duration_s: Optional[float] = Field(default=None)
    started_at: Optional[dt.datetime] = Field(default=None)
    finished_at: Optional[dt.datetime] = Field(default=None)
    created_by_user_id: Optional[int] = Field(default=None)
    created_at: dt.datetime = Field(
        default_factory=lambda: dt.datetime.now(dt.timezone.utc)
    )


class TranscriptionResult(SQLModel, table=True):
    """Ergebnis eines TranscriptionRun (Change 094): text + segments."""

    id: Optional[int] = Field(default=None, primary_key=True)
    run_id: int = Field(foreign_key="transcriptionrun.id", index=True)
    text: Optional[str] = Field(default=None)
    segments: Optional[List[Any]] = Field(default=None, sa_column=Column(JSON))
    created_by_user_id: Optional[int] = Field(default=None)
    created_at: dt.datetime = Field(
        default_factory=lambda: dt.datetime.now(dt.timezone.utc)
    )


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
    # --- Change 086: virtuelle Credits (Zugangskontrolle) ---
    # server_default, damit auch rohe SQL-Inserts (Tests/Migrationen) ohne
    # die Spalten funktionieren (NOT NULL sonst verletzt).
    credits_cents: int = Field(
        default=0, sa_column_kwargs={"server_default": "0"}
    )
    tier: str = Field(
        default="test", sa_column_kwargs={"server_default": "'test'"}
    )  # free | paid | test (test = virtuelles Guthaben)
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
    ``expires_at`` begrenzt die Gültigkeit (Default: 1 Jahr ab Erstellung);
    abgelaufene Keys werden von der Authentifizierung abgelehnt.
    """
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    name: str = "default"
    description: Optional[str] = None
    level: str = "read"
    token_hash: str = Field(index=True, unique=True)
    expires_at: Optional[dt.datetime] = None
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


class Annotation(SQLModel, table=True):
    """Change 056 — zeitgebundener Kommentar zu einer Transkription.

    Eine Annotation hängt an einer Text-Markierung (segment_idx +
    char_start/char_end) und deren Zeitfenster (start_s/end_s, aus den
    Wort-Timestamps abgeleitet). ``body`` ist Markdown; Antworten (Threads)
    referenzieren via ``parent_id`` die Top-Level-Annotation (eine Ebene).
    """

    id: Optional[int] = Field(default=None, primary_key=True)
    uid: str = Field(
        default_factory=lambda: uuid.uuid4().hex,
        unique=True,
        index=True,
    )
    rec_id: int = Field(foreign_key="recording.id", index=True)
    user_id: Optional[int] = Field(default=None, foreign_key="user.id", index=True)

    # --- Markierung ---
    segment_idx: int = 0
    char_start: int = 0
    char_end: int = 0
    #: Zeitfenster (Sekunden, Original-Zeitbasis) — aus Wort-Timestamps
    #: abgeleitet; Fallback: Segment-Grenzen.
    start_s: float = 0.0
    end_s: float = 0.0

    #: Kommentar (Markdown). Antworten: parent_id = Top-Level-Annotation.
    body: str = ""
    parent_id: Optional[int] = Field(default=None, foreign_key="annotation.id", index=True)

    created_at: dt.datetime = Field(
        default_factory=lambda: dt.datetime.now(dt.timezone.utc)
    )
    updated_at: dt.datetime = Field(
        default_factory=lambda: dt.datetime.now(dt.timezone.utc)
    )


class CreditLedger(SQLModel, table=True):
    """Change 086 — append-only Buchungs-Journal der virtuellen Credits.

    Eine Zeile je Buchung (topup/job_cost/refund/signup_bonus). Nichts
    wird gelöscht; bei User-Löschung werden die Zeilen anonymisiert
    (user_id → NULL), die Summen bleiben erhalten.
    """
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: Optional[int] = Field(default=None, foreign_key="user.id", index=True)
    delta_cents: int = 0
    reason: str = "job_cost"  # topup | job_cost | refund | signup_bonus
    ref_id: Optional[int] = None       # Recording-/Job-ID bei job_cost
    created_at: dt.datetime = Field(
        default_factory=lambda: dt.datetime.now(dt.timezone.utc)
    )
    created_by: Optional[int] = None   # Admin-User-ID bei topup/refund


class RtfEstimate(SQLModel, table=True):
    """Change 085 — persistierte Lern-Historie der ETA-Faktoren.

    Eine Zeile je Phase-Key (z. B. ``asr:ps-pk-onnx``, ``diar:pyannote``,
    ``align``). Die rollende Stichproben-Historie liegt als JSON in
    ``history_json``; ``digest`` invalidiert bei Backend-Image-Wechsel.
    Schätzwerte (factor/low/high) berechnet der rtf_learner live aus der
    Historie — keine gecachten Anzeige-Werte.
    """
    phase_key: str = Field(primary_key=True)
    history_json: str = "[]"            # rollende Faktor-Stichproben
    digest: Optional[str] = None
    updated_at: dt.datetime = Field(
        default_factory=lambda: dt.datetime.now(dt.timezone.utc)
    )
