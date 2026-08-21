# Code-Guide: PolySchnack verstehen

Diese Anleitung erklärt das komplette Repo: **welche Dateien existieren,
was sie tun und wie sie zusammenspielen**. Zielgruppe: jemand, der den
gesamten Code verstehen will (Einsteiger in den Code wie auch
Weiterentwickler). Sie ergänzt die [Architektur](../architecture.md)
(Systemebene) um die Code-Ebene.

## Repo-Überblick

```
polyschnack/
├── compose*.yml              # Container-Definitionen (Kern, Backends, GPU, OIDC, Benchmark)
├── polyschnack-manage.sh     # Stack-Verwaltung (start/stop/models/update/benchmark/…)
├── webapp/                   # DIE Webapp: FastAPI-Backend + React-Frontend
│   ├── app/                  # Backend (Python, FastAPI + SQLModel)
│   ├── frontend/             # Frontend (React 18 + TypeScript + Vite)
│   └── tests/                # Backend-Tests (pytest, ~15.500 Zeilen)
├── approach-a/               # ONNX-ASR-Service: Parakeet (Standard-Backend, :5092)
├── pk-asr-cpp/ qwen3-asr-cpp/ ark-asr-cpp/ canary-asr-cpp/ moonshine-de-cpp/
│                             # CrispASR-basierte Backend-Images (Dockerfiles + Entrypoints)
├── diar-service/             # CrispASR-Diarization-Container
├── aligner-service/          # Forced-Aligner-Service (Word-Timestamps)
├── ps-tor/                   # Tor-Sidecar (YouTube-Import-Fallback)
├── scripts/                  # CI-Helfer (Versionierung, Smart-Build)
├── openspec/                 # Spezifikation + Change-Proposals (siehe Entwicklung)
├── docs/                     # Diese Dokumentation (MkDocs)
└── DATA/                     # Laufzeit-Daten (nicht im Git): SQLite, Audio, Modelle
```

---

## 1. Backend (`webapp/app/`)

FastAPI-App mit SQLModel/SQLite. Einstieg: `main.py` (App-Factory,
Startup-Diagnose, Router-Mounts).

### Kern-Module

| Datei | Funktion |
|---|---|
| `main.py` | App-Factory, Startup: DB-Migration, Modell-Diagnose, Stale-Job-Watchdog, Backfill-Loops |
| `config.py` | **Alle Env-Variablen** zentral (Settings-Model, Defaults) — siehe [Env-Variablen](../configuration/env.md) |
| `models.py` | SQLModel-Tabellen: `Recording`, `User`, `RecordingShare`, `Annotation`, `VersionItem`, `DeliveryTarget`, `ApiKey`, `PromptTemplate`, `LlmEndpoint` … |
| `db.py` | Engine/Session, WAL-Modus, Auto-ALTER (fehlende Spalten nachtragen), VACUUM-Helfer |
| `crud.py` | Datenzugriffe (Recording-CRUD, Shares, Queue-Position, …) |
| `deps.py` | FastAPI-Dependencies: `get_session`, `require_authenticated`, `require_admin` (nur bei `OIDC_ENABLED`) |
| `permissions.py` | Zugriffsmodell: `access_level` (owner/full/write/read) pro Recording, `ensure_access` |
| `identity.py` / `anon_session.py` / `anon_names.py` | Session-/User-Logik, anonyme Nutzer (zufällige Namen, Limits) |
| `service.py` | **Transkriptions-Pipeline**: Upload-Verarbeitung, ASR-Aufruf, Align, Diar-Merge, Versionen, Post-Processing-Orchestrierung |
| `service_registry.py` | Registry-Loader für `backends.yaml` (validiert Capabilities) |
| `asr_client.py` + `asr_client/` | **Adapter-Pattern**: eine Klasse pro Backend-Protokoll, Factory `get_client()` |
| `queue.py` | Transcribe-Queue (pro Backend seriell, Prioritäten, ETA, Cancel) |
| `dispatcher/` | Job-Dispatching: `scheduler.py`, `backends/`, `costs.py` (Kosten je Backend) |
| `diarize.py` | HTTP-Client für den `crispr-diar`-Container (kein pyannote mehr im Image) |
| `aligner_client.py` | HTTP-Client für den Forced-Aligner (`crispr-align`) |
| `docker_proxy.py` | Restriktive Docker-Steuerung (start/stop/status der Backend-Container) |
| `resources.py` | Ressourcen-Check vor Backend-Start (RAM/Disk/VRAM) |
| `peaks.py` | Wellenform-Peaks berechnen (numpy, 16 kHz mono) |
| `vad.py` | Silero-VAD-Trimmung (externer Service) |
| `retention.py` / `orphan_sweep.py` | Auto-Löschung öffentlicher/abgelaufener Daten, verwaiste Dateien |
| `recording_health.py` | Self-Healing: fehlende Audio-Dateien erkennen und markieren |
| `llm.py` / `llm_url.py` | LLM-Aufrufe (Punctuation, Enhance, Templates); SSRF-Prüfung für BYOK-URLs |
| `deliver.py` | Delivery-Targets: E-Mail (SMTP) + WebDAV (Nextcloud) |
| `export.py` / `export_backup.py` / `export_templates/` | Export: TXT/SRT/VTT, Backup-ZIP, dynamische Export-Templates |
| `crypto.py` | Fernet-Verschlüsselung (Secrets, SMTP-Passwörter, API-Keys) |
| `versions.py` | Versions-History + Diff pro Recording |
| `benchmark_service.py` | Benchmark: versionierte Manifeste, Sample-Verwaltung, Ergebnisse |
| `pricing.py` | Benchmark-Preisvergleich (Selbstkosten × markup) |
| `stale_jobs.py` | Watchdog: hängende Jobs nach Timeout als failed markieren |
| `whatsapp.py` | WhatsApp-Gruppen-Integration (optional) |
| `yjs/` | Kollaborative Bearbeitung: Yjs-WebSocket-Räume (`rooms.py`) |
| `worker/` | Hintergrund-Worker-Helfer (z. B. `crypto.py` für verschlüsselte Worker-Secrets) |

### Router (`app/routers/`)

| Router | Endpunkte |
|---|---|
| `recordings.py` | Upload, Liste (`?lite=1`), Detail, Transcribe/Retranscribe, Delete, Titel, Tags, Anon-Link, Audio/Preview/Download/Backup |
| `segments.py` | Segment-PUT (Persistenz nach Edit/Drag/Split) |
| `queue_api.py` | Queue-Ansicht (Position, ETA, fremde Jobs anonymisiert) |
| `cancel.py` | Job-Cancel |
| `models.py` | Modell-/Backend-Diagnose, `/api/models/matrix`, `/api/models/status` |
| `matrix.py` | Feature-Matrix der Backends (für GUI + Admin) |
| `admin.py` | Admin-Bereich: Services starten/stoppen, Config (Default-Backend), VACUUM |
| `auth.py` | OIDC-Login/-Callback/-Logout, `/auth/me` |
| `shares.py` | User-Shares (read/write/full) |
| `annotations.py` | Zeitgebundene Kommentare + Threads (Change 056) |
| `versions.py` | Versionen, Diff, Restore |
| `benchmark.py` | Öffentliche Benchmark-Daten + Admin-POSTs (reject/edit) |
| `keys.py` | API-Keys |
| `llm_endpoints.py` | BYOK-LLM-Endpunkte (verschlüsselt, SSRF-geprüft) |
| `templates.py` / `targets.py` | Prompt-Templates + Delivery-Targets |
| `url_import.py` | YouTube/URL-Import (yt-dlp, Tor-Fallback-Kaskade) |
| `openai_proxy.py` | **OpenAI-kompatibler Proxy**: `POST /v1/audio/transcriptions` → Backend-Wahl |
| `account.py` | User-Konto-Einstellungen |
| `api_docs.py` / `recovery.py` | OpenAPI-Doku / Boot-Recovery |

### Das Adapter-Pattern (wichtig!)

`webapp/app/asr_client/` enthält eine Klasse pro Backend-Protokoll:

| Adapter | Backends | Protokoll |
|---|---|---|
| `pk_python.py` | ps-pk-onnx | ONNX-Service (verbose_json) |
| `pk_cpp.py` | crispr-pk-cpp | CrispASR parakeet |
| `qwen3_asr_http.py` | crispr-qwen3 | CrispASR qwen3 |
| `crisp_asr_http.py` | ark, moonshine-de, canary, voxtral, whisper | CrispASR (Capabilities per `adapter_kwargs` überschrieben) |
| `openai_compat_http.py` | Remote-Backends (whisper-large-v3, voxtral-mini-realtime) | OpenAI-kompatible REST-APIs |

**Neues Backend = 3 Stellen:** (1) Block in `webapp/app/backends.yaml`
(Registry: Name, Port, `model_files`, Capabilities, Adapter),
(2) Service in `compose.backends.yml`, (3) ggf. Adapter. `get_client()`
dispatcht über die Registry, NICHT über hartkodierte Namen — jeder Adapter
hat seine **eigene URL-Env** (`CRISPR_QWEN3_URL`, …), nie `ASR_URL`
(der ist der ONNX-Container).

### Request-Lifecycle (Backend)

```
Browser/API → Router (recordings.py)
  → crud.create_recording → queue.enqueue (per Backend, Kapazität 1)
  → dispatcher/scheduler → service.process_recording
      → Adapter (asr_client)  → ASR-Backend (HTTP)
      → aligner_client        → crispr-align (Wortgrenzen)
      → diarize.py            → crispr-diar (Sprecher, optional)
      → service._merge_diarization (Wort-Stream-Kaskade)
      → Post-Processing (Punct/LLM/Delivery, opt-in)
      → Version anlegen, Cache invalidieren
  → Frontend pollt (2 s) /api/recordings → Status + Text + Fortschritt
```

---

## 2. Frontend (`webapp/frontend/src/`)

React 18 + TypeScript + Vite, React-Query (Server-State), Tailwind. Die
**i18n** läuft über `useLocale.ts` (3 Blöcke: de/en/pt-BR; fehlende Keys
fallen auf den Key-Namen zurück).

### Einstieg

| Datei | Funktion |
|---|---|
| `main.tsx` / `App.tsx` | App-Bootstrap, Layout, Tabs (Upload/Liste), Header, Sprachwähler |
| `api.ts` | **Alle Backend-Aufrufe** (fetch-Wrapper mit Fehler-Detail aus `detail`) + Typen (`Recording`, `Segment`, …) |
| `hooks.ts` | React-Query-Hooks: `useRecordings`, `useRecordingDetail`, `useStats`, `useDelete`, … |
| `useLocale.ts` | Übersetzungen + `useT()` |

### State & Datenfluss

- **`useRecordings`** holt die Liste mit `lite=1` (nur Karten-Metadaten,
  Change 059) — pollt alle 2 s, solange irgendeine Aufnahme
  `processing` ist.
- **`useRecordingDetail(uid, enabled)`** lädt Transkription + Peaks pro
  Karte beim Aufklappen (`GET /api/recordings/{uid}`), gecacht pro `uid`.
- **Edits** (`handleEdited` in `RecordingCard.tsx`) schreiben optimistisch
  in **beide** Caches (Liste + Detail) und persistieren per PUT `/segments`.
- **Kollaboration**: `useYjsTranscription` (`hooks/useYjsTranscription.ts`)
  synchronisiert Segment-Text über Yjs-WebSocket-Räume; beim Beenden wird
  als Version persistiert.

### Pure Logik (unit-getestet, ohne DOM)

| Datei | Funktion |
|---|---|
| `karaoke.ts` | Wort-Highlight, aktives Segment, Wort-Navigation, Confidence-Farben |
| `resegment.ts` | Segment-Logik: teilen (`splitSegmentAtRange`), löschen, Grenzen verschieben, Auto-Re-Segmentierung |
| `share.ts` | Share-URL-Helfer (`buildShareUrl`, `parseSharePath`, `formatExpiry`) |
| `benchmark.ts` | Benchmark-API + Pfad-Erkennung |
| `format.ts` | Formatierung (Bytes, Dauer, Zeitstempel), `abbreviateMid` |
| `grouping.ts` / `sortState.ts` | Listen-Gruppierung + Sortierung (Change 054) |
| `versionDiff.ts` | Versions-Diff-Typen |
| `offlineQueue.ts` | Offline-Aufnahmen puffern (Upload bei Wiederverbindung) |
| `audioSession.ts` | iOS-AudioSession-Handling (Mikro/Playback) |
| `backendSelect.ts` | Backend-Auswahl (Admin: alle; Anon: nur laufende) |
| `diarizeParams.ts` | Diarize-Tuning-Mapping (Sensitivität → `min_duration_off`) |
| `useDismiss.ts` / `useFlipUp.ts` / `clipboard.ts` / `splitPosition.ts` | Popover-Schließen/Flip, Clipboard-Fallback, Split-Popover-Position (Change 058) |

### Komponenten (`components/`)

| Komponente | Funktion |
|---|---|
| `RecordingCard.tsx` | **Die zentrale Karte**: Header, Player, Transkript, Aktionen (Download/Share/Versionen/Delete/Re-Transcribe), Annotate-Popover, Detail-Nachladen |
| `RecordingList.tsx` | Liste + Gruppierung + Sortier-Badges |
| `SegmentList.tsx` | Transkript-Ansicht: Karaoke, Edit, Split-Symbol, Speaker-Menü, Drag-Grenzen |
| `SegmentSearch.tsx` | Suchen/Ersetzen im Transkript |
| `WaveformPlayer.tsx` | WaveSurfer: Peaks, Zoom, Regionen, Annotation-Marker, Lazy-Load |
| `FeatureToggles.tsx` / `ImportToggles.tsx` / `TuningPopover.tsx` | Transcribe-Optionen (VAD/Diar/Live/NR/Enhance) + Diarize-Tuning |
| `UploadZone.tsx` | Upload (Drag&Drop, Mikro-Recording, URL-Import), Duplikat-Dialog, Help-Modal |
| `AdminPanel.tsx` | Admin: Backends starten/stoppen, Config, Modell-Matrix |
| `SharedRecordingView.tsx` | Öffentliche Share-Ansicht (`/r/:uid`) |
| `AnnotationThreads.tsx` | Kommentar-Threads (Markdown, Mentions) |
| `Toasts.tsx` | Toast-System (ok/err, animiert) |
| `BenchmarkPage.tsx` | Öffentliche Benchmark-Seite |
| `QueueWatcher.tsx` | Queue-Status + ETA |
| `StatsBar.tsx` / `SearchBar.tsx` / `TagEditor.tsx` / `VersionDiff.tsx` / `WhatsappGroup.tsx` / `ApiKeysSection.tsx` / `UserSettingsPage.tsx` / `InstallBanner.tsx` / `PostProcessPanel.tsx` / `ImportToggles.tsx` | weitere UI-Bausteine |

### Frontend-Tests

Vitest (`src/*.test.ts`, `components/*.test.tsx`). Konvention: reine Logik
als pure Funktionen testen; Komponenten mit @testing-library. API-Aufrufe
werden gemockt (keine Netz-Tests).

---

## 3. ASR-Dienste (eigene Container)

| Verzeichnis | Zweck |
|---|---|
| `approach-a/` | **Standard-Backend** ps-pk-onnx: ONNX-Runtime-Service (`polyschnack_service/`: `model.py` Modell-Wahl GPU/CPU, `routes.py` OpenAI-kompatible API, `chunker.py` Chunking, `batchworker.py` async-Jobs) |
| `pk-asr-cpp/` | parakeet.cpp via CrispASR (hybrides Image, `CRISPASR_EXTRA_ARGS` für Punct/Truecase) |
| `qwen3-asr-cpp/` | Qwen3-ASR + Forced-Aligner (CrispASR) |
| `ark-asr-cpp/` | ARK-ASR (CrispASR) |
| `canary-asr-cpp/` | Canary (CrispASR) |
| `moonshine-de-cpp/` | Moonshine-DE (CrispASR) |
| `diar-service/` | CrispASR-Diarization-Server (Modell-Auto-Download via `entrypoint.sh`) |
| `aligner-service/` | Forced-Aligner: `POST /v1/audio/align` (Audio + Referenztext → Wortgrenzen) |
| `ps-tor/` | Tor-Sidecar: SOCKS5 für YouTube-Download-Fallback (Change 043) |

Alle CrispASR-Container teilen das Modell-Volume `./DATA/models` (read-only)
und starten den Server-Modus (`crispasr --server -m <GGUF> --port <Port>`).

---

## 4. Betrieb & CI

### `polyschnack-manage.sh`

Zentrale Stack-Verwaltung (ersetzt `start.sh`): `pull`, `start`, `stop`,
`restart`, `down`, `status`, `logs`, `models`, `benchmark`, `key`, `update`,
`selfupdate`, `help`. Details: [Quickstart](../quickstart.md).

### `scripts/`

- `ci_version.sh` — CalVer-Tag-Berechnung (`YYYY.M.N` aus Registry-Tags)
- `ci_smart_build.sh` — Build-Skript: nur bauen, wenn der SHA fehlt;
  Tagging `latest`/`YYYY`/`YYYY.M`/`YYYY.M.N`
- `calibrate_vram_limit.py` — VRAM-Limit-Kalibrierung fürs Long-Audio

### CI (`.gitlab-ci.yml`)

Stages `test → build → pages`: `test-core` (approach-a), `test-webapp`
(Backend-Suite), `test-frontend` (Vitest), `compose-validate` (YAML-Check),
Build-Jobs je Image (`build-asr`, `build-cpp`, `build-qwen3`, `build-ark`,
`build-diar`, `build-webapp`, …), `version-tag` (CalVer), `mirror-ghcr`
(Public-Mirror), `pages` (MkDocs `--strict`). GitHub-Mirror: identische
Tests via GitHub Actions (`.github/workflows/ci.yml`).

### Tests

- Backend: `webapp/tests/` (~150 Dateien, pytest; `DATA_DIR` MUSS vor dem
  App-Import gesetzt sein — siehe `tests/conftest.py`).
- Frontend: Vitest (siehe oben).
- End-to-End-Yjs: `e2e-yjs/` (zwei Clients gegen lokalen Server).

---

## 5. Spezifikation & Change-Management

- `openspec/project.md` — Projekt-Überblick + External Systems
- `openspec/specs/*/spec.md` — Capabilities (Transcription, Sharing,
  Backend-Queue, Post-Processing, Identity, Benchmark, Versioning, …)
- `openspec/changes/<NNN>-<slug>/proposal.md` — **jede** Feature-Änderung
  als Change-Proposal (History 001–059, Archiv unter `archive/`)

Regel: **Neues Feature → neues Change-Proposal im selben Commit** wie der
Code. Details: [Entwicklung/OpenSpec](openspec.md).

---

## Schnellstart für Code-Leser

1. **Wo passiert Transkription?** `webapp/app/service.py` →
   `process_recording` (Kern der Pipeline).
2. **Wo ist das UI?** `webapp/frontend/src/components/RecordingCard.tsx`
   (Karte) + `App.tsx` (Layout).
3. **Wie kommt ein Backend dazu?** `webapp/app/backends.yaml` →
   `compose.backends.yml` → Adapter.
4. **Was wurde wann geändert?** `openspec/changes/` (pro Change:
   Proposal mit Problem/Ziel/Umsetzung) + Git-History.
