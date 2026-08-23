# Tasks — Change 094 (runs → results, Etappe 1)

## Offene Fragen
- Keine — Design in proposal.md festgehalten; Etappe 2/3 als Folge-Change.

## Tasks

### 1. Modelle (app/models.py)
- [ ] `TranscriptionRun` (table): rec_id (FK, index), Settings-Snapshot
  (backend, language, enable_vad, enable_diarize, diarize_num_speakers,
  diarize_min_duration_off, diarize_method, enable_streaming,
  enable_noise_reduce, enable_enhance, enable_punctuation, enable_llm_enhance,
  llm_endpoint_id, prompt_template_id), status (queued|processing|done|failed),
  progress_pct, phase, error, duration_s, started_at, finished_at,
  created_by_user_id, created_at.
- [ ] `TranscriptionResult` (table): run_id (FK, index), text, segments (JSON),
  created_by_user_id, created_at.
- [ ] `Recording`: + `current_run_id`, `current_result_id` (FK, nullable);
  Deprecation-Kommentar an Settings-/Ergebnis-Spalten (Etappe 2: DROP).

### 2. Run/Result-Lebenszyklus (app/service.py)
- [ ] Job-Start (nach Settings-Read, Z. ~1396): `TranscriptionRun` anlegen
  (status=processing, created_by_user_id=owner_id), `started_at`; lokale
  run_id merken.
- [ ] Abschluss: `TranscriptionResult` (text/segments) + Run auf done +
  duration_s/language + finished_at; Recording.current_run_id/
  current_result_id + Spiegel (text/segments/backend/language) in einer
  Transaktion.
- [ ] Fehlerpfad im Job (status=failed, Z. ~1729/1733): aktiven Run auf
  failed + error setzen.
- [ ] `_abort_recording` (Z. 1265): aktiven Run failed + error.

### 3. API (app/routers/recordings.py)
- [ ] `GET /api/recordings/{rid}/runs` (Owner/Admin, User-Isolation):
  neueste zuerst, Settings-Snapshot + Status + Zeiten + result_id +
  Segment-Anzahl (aus Result.segments).
- [ ] `GET /api/recordings/{rid}/runs/{run_id}`: Run + volles Result.

### 4. Tests
- [ ] Run-Erzeugung beim Transcribe (Fake-Job-Pfad): Settings im Run ==
  rec-Settings; Result.text/segments == Job-Ergebnis; Zeiger gesetzt.
- [ ] Re-Transcribe erzeugt zweiten Run; erster bleibt erhalten.
- [ ] Fehlerpfad: Job-Fehler → Run failed + error; _abort_recording → failed.
- [ ] API-Tests: runs-Liste (Sortierung, Isolation, 404/403).

### 5. Abschluss
- [ ] Backend-Testsuite komplett grün (inkl. Bestand).
- [ ] openspec validate 094-runs-results.
- [ ] Commit + Push, CI-Watch bis success.
- [ ] Mnemosyne: Design-Entscheidung runs/results + Etappen festhalten.
