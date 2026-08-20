# Change 035 — Tasks

## Backend

- [x] service.py: Heartbeat-Fallback — Bedingung `if not async_jobs` → startet Heartbeat bei JEDEM nicht-streamenden Pfad (auch async_jobs=True mit Sync-Fallback)
- [x] service.py: Heartbeat liest aktuellen pct aus der DB (kein Rückschritt bei on_progress)
- [x] service.py: vor LLM-Phasen (run_punctuation / run_llm_enhance / Template-Call) `set_progress(95, "postprocessing")` + Heartbeat-Thread
- [x] crud.py: `set_queued` + `set_processing` setzen `last_heartbeat_at = now` und `phase_started_at = now`
- [x] Tests (pytest): Heartbeat tickt bei gemocktem blockierendem `transcribe()` mit async_jobs=True; set_queued/set_processing reseten Heartbeat-Felder → 6 passed

## Frontend

- [x] RecordingCard: Phasen-Chips (preparing → asr → diarization → alignment → postprocessing) mit Status erledigt/aktiv/übersprungen/offen
- [x] Aktive Phase aus progress_note (+ pct-Fallback); diarization-Chip „übersprungen" bei enable_diarize=false
- [x] Stall-Text: „möglicherweise hängend · keine Aktivität seit Xs"
- [x] Tests (vitest): activePhaseIndex aus note/pct → 8 passed; Gesamt-Frontend-Suite 182 passed

## Abschluss

- [ ] Commit + Push → CI-Build (webapp-Image)
- [ ] CI-Pipeline prüfen und melden
- [ ] Nach Deploy: Live-Transkription auf der Box beobachten — keine Stall-Warnung mehr bei laufendem Job, Chips zeigen Phasen
