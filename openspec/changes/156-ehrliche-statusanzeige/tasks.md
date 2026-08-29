# Change 156 — Ehrliche Statusanzeige: Tasks

## Schritt 1 — Backend: Status aus der Job-Tabelle ableiten (done)
- [x] `_active_job_for_rec` + `_reconcile_stale_statuses` (recordings.py)
- [x] `_recording_to_dict`: `status=processing` + `phase` bei aktivem Job;
      `queue_position` aus dem Job (nicht rec.status)
- [x] Reconcile-Aufruf in der List-Route (stale processing → done/failed)
- [x] `queue.py list()`: `kind` + `progress_pct` + `progress_note` je Job

## Schritt 2 — Frontend (done)
- [x] i18n phase-Keys (de/en/pt-BR): transcribe/align/rediarize/peaks/vad
- [x] StatusBadge: Phase-Label + echter Fortschritt (kein generisches
      "in Arbeit" ohne Kontext)
- [x] QueueWatcher: Phase + Fortschritt statt "in Arbeit…"; Backend-Badge
      nur bei queued; laufende Diarization (progress_note) wird als
      Phase angezeigt (Befund "falscher Prozess")

## Schritt 3 — Tests (done)
- [x] `test_status_honesty.py`: Reconcile (stale→done/failed, aktiver Job
      bleibt), Phase im Payload, kein Job → kein Phase
- [x] Frontend 392/392, tsc clean, Queue/Delete-Tests 31/31

## Schritt 4 — Folgepunkt (NICHT Teil dieses Commits)
- [ ] **Diarization als eigener Queue-Job** (`kind=diarize`, Backend
      `crispr-diar`): der transcribe-Job macht nur noch ASR; danach
      enqueue diarize-Job (bei enable_diarize). Ermöglicht granulares
      Scheduling (Phasen einzeln in der Queue, unterschiedliche Backends)
      und macht die Queue-Zeile automatisch phasen-echt. Umbau betrifft
      den stabilen Transkriptions-Workflow → eigener Change mit
      sorgfältigen Tests (Segment-/Speaker-Zuordnung bleibt 1:1).
