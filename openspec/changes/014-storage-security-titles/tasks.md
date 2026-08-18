# Change 014 — Tasks

TDD-Reihenfolge: Backend-Tests zuerst (webapp/.venv), dann Frontend.

## Phase 1: Modell + Migration

- [ ] `Recording`: Felder `title: Optional[str]`, `owner_user_id: Optional[int]`
      (index) ergänzen; ALTER-TABLE-Helper (Muster Change 009) in den
      Startup-Migrationsblock aufnehmen.
- [ ] `_recording_to_dict`: `title` (Fallback original_name) + `owner_user_id`
      ausliefern.

## Phase 2: User-Ordner

- [ ] `audio_utils.storage_path_for(user_id, ext)` + Test (user_id None → anon).
- [ ] Upload-Endpoint (`routers/recordings.py`), Crop (`transcribe-range`),
      Re-Transcribe-Ergebnis, `url_import.py`: `stored` via
      `storage_path_for(uid, ext)`.
- [ ] Test: Upload → Datei unter `AUDIO_DIR/<uid>/`; Legacy-`stored_path`
      bleibt lesbar (Playback-Test mit altem Pfad).

## Phase 3: Self-Healing + Lösch-Rechte

- [ ] `recording_health.py`: `scan_broken(session, audio_dir)` — fehlende
      Datei / Magic-Bytes / Mindestgröße → Liste kaputter (id, uid, reason).
      `mark_broken(session, ids)` setzt failed + Fehlertext.
- [ ] Startup-Hook in `main.py` (wie stale_jobs) + täglicher Lauf (Config-
      Flag `HEALTH_SCAN_ENABLED`, default true; `HEALTH_MIN_AGE_S`).
- [ ] `permissions.py`: Owner = `rec.user_id` oder `rec.owner_user_id`;
      `recovery_restore` setzt `owner_user_id` (Admin-Request → aktueller
      User, sonst None); anon-Uploads setzen `owner_user_id=uid`.
- [ ] DELETE/Re-Transcribe: `ensure_access` mit neuem Owner-Fallback;
      Audio-Endpoint: fehlende Datei → 404 mit klarer Message.
- [ ] Tests: kaputte Recording → failed nach Scan; DELETE auf
      `user_id=None` + `owner_user_id` gesetzt → ok; ohne Owner → 403.

## Phase 4: Titel + Sidecar + Frontend

- [ ] `audio_utils`: `read_sidecar(path)` / `write_sidecar(path, title,
      original_name)` + Tests.
- [ ] PATCH `/api/recordings/{rid}` (title) — Owner/Admin; schreibt DB +
      Sidecar (best-effort).
- [ ] `api.ts`: `Recording.title?`, `updateRecordingTitle()`.
- [ ] `RecordingCard.tsx`: Titel editierbar (Stift/Inline-Input); zweite
      kleine Zeile mit `original_name`, wenn `title !== original_name`;
      Defekt-Badge bei `status==="failed" && /Audio-Datei fehlt/.test(error)`;
      Delete auch bei defekten Einträgen aktiv.
- [ ] Frontend-Tests (vitest): Titel-Edit-Render, zweite Zeile, Badge.

## Phase 5: Verifikation + CI

- [ ] `SESSION_SECRET=... webapp/.venv/bin/python -m pytest webapp/tests/...`
      (alle grün).
- [ ] `npx vitest run` (142+ neu), `npx tsc --noEmit`.
- [ ] Playwright: Titel ändern → zweite Zeile; kaputte Recording (Mock) →
      Badge + Delete ok.
- [ ] `openspec validate 014-storage-security-titles` grün; Commit + Push;
      CI-Watchdog; Deploy-Hinweis.
