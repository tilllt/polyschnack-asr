# Change 115 — Live-Progress & RTF bei Hintergrund-Vorgängen: Tasks

## Phase 1 — Backend

- [x] Re-Diarize-Worker (`_run_background_rediarize`): `_start_job_heartbeat`
      starten (last_heartbeat_at-Tick), Stop in allen Ausgangspfaden
- [x] Re-Diarize-Worker: RTF-Stichprobe (diar-Phasen-Zeit) an
      learner_store.ingest_job_sample (Key `diar:<method>` wie Haupt-Job)
- [x] Align-Worker: verifiziert — set_progress tickt last_heartbeat_at
      (crud Z. 549), kein zusätzlicher Tick nötig

## Phase 2 — Frontend

- [x] RecordingCard: bg-align-Hinweis → Heartbeat-Ampel + phaseDetail
      („Gruppe X/Y — aktiv seit … — CLI 45%", enthält Align-RTF-Ausgabe);
      Fallback-Text mit „läuft seit Xs" wenn keine Note
- [x] RecordingCard: bg-diar-Hinweis → Heartbeat-Ampel + „läuft seit Xs"
- [x] i18n: phase_running_since / heartbeat_ago existieren bereits

## Phase 3 — Tests + Verifikation

- [x] Frontend: RecordingCard-Tests (bg-align mit phaseDetail, bg-diar mit
      Heartbeat-Zeit) — 309/309 + tsc 0
- [x] Backend: Testsuite grün
- [x] Commit + Push, CI prüfen

## Befund (24.08.)

- Live-Block nur bei status processing (Z. 1390); done+alignment-running
  zeigte statischen Text (Z. 1231), obwohl Worker Noten/Heartbeat schreibt.
- set_progress tickt last_heartbeat_at (crud 549); note=None lässt Note
  stehen (crud 550) → Job-Heartbeat überschreibt Noten nicht.
- Align-Worker ingestet bereits ingest_align_sample (service 904).
- Re-Diarize setzte progress_note direkt (service 1371), kein Heartbeat →
  jetzt `_start_job_heartbeat` + RTF-ingest (Change 115).
