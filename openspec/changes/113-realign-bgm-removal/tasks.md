# Change 113 — Re-Align mit BGM-Removal: Tasks

## Phase 1 — Backend

- [x] `segments.py realign_recording`: `separate_backend: str = Form("none")` +
      `isinstance`-Guard (direkte Aufrufer in Tests) + Durchreichung an
      `_schedule_realign(rec.id, separate_backend)`
- [x] `service.py _schedule_realign(rec_id, separate_backend="none")`:
      Separation nach VAD-Trim/Enhance einfügen (SeparateClient-Logik wie
      service.py Z. 1569–1588: health → separate → vocals, ehrlicher
      Fallback Original), Alignment-Cache mit vocals + trim_offset_s
- [x] Regressionstests: realign mit/ohne Feld (Form), Guard, Fallback
      (test_realign_routes.py, 5 Tests — 9/9 mit Change-106-Suite grün)

## Phase 2 — Frontend

- [x] `api.ts realignRecording(id, opts?)`: FormData mit `separate_backend`
      (analog transcribe, api.ts Z. 398)
- [x] `hooks.ts useRealign`: Typ `{ id, opts }` statt `string`
- [x] `RecordingCard.tsx`: Sep-Auswahl (aus/htdemucs/melband) neben dem
      Re-Align-Button; Wert wird bei `handleRealign` mitgesendet
- [x] Frontend-Tests: Select vorhanden, FormData enthält Feld
      (RecordingCard.test.tsx, 2 neue Tests — 26/26 Datei, 307/307 gesamt)

## Phase 3 — Verifikation

- [x] Backend-Gesamtsuite grün (965: 958 + 2 reparierte test_realign-Mocks + 5 neue)
- [x] Frontend-Suite grün (307/307), tsc 0
- [x] Commit + Push (`0aaf4b9`), CI läuft (Watchdog)

## Befund (24.08.)

- Produktion: `align_available: True` (`/api/models/status`, crispr-align:5099
  erreichbar) — der Aligner-Service läuft; die Lücke ist die Re-Align-Route
  (kein `separate_backend`) und `_schedule_realign` (kein Music-Removal).
- UI zeigt bei `alignment=skipped` seit Change 101 „⚠️ Alignment übersprungen".
