# Tasks — Change 110 (Workflow-Scheduling-Refactoring)

## Konzept (dieser Change)
- [x] proposal.md: Befunde S1–S7 + Ziel-Architektur K1–K6 + Abhängigkeiten
- [x] Commit + Push
- [ ] Review mit User (Workflow-Liste, Retry-Politik pro Workflow-Typ)

## Folge-Change (Umsetzung, nach 109-Konzept-OK; baut auf Job-Runner)
- [ ] Phasen-Enum + WORKFLOWS-Registry (Phase: name/pct_range/cancel/timeout/io)
- [ ] process_recording in `run_workflow(rec_id, workflow, step, range, job)` zerlegen
- [ ] align/rediarize als Queue-Jobs (fire-and-forget-Threads entfernen)
- [ ] Ein Heartbeat-Muster (drei Kopien ersetzen)
- [ ] Phasen-Zeiten pro Run persistieren (rtf_learner/ETA aus echten Werten)
- [ ] SCHEDULED_TASKS-Registry (sweep/peaks/health; Router-Fire-and-forget entfernen)
- [ ] Assertion „Workflow nur mit Job" + Grep-Gate in CI (keine nackten Threads in service.py)
- [ ] Reprocess-Smoke-Test (108): Bereichs-Align verändert nur den Bereich

## Offene Fragen (Review)
- Retry-Politik je Workflow-Typ: align/rediarize automatisch 1× oder nur manuell?
- Sollen Background-Workflows die Queue-Kapazität der ASR-Backends belegen
  (eigenes Semaphore „postprocessing")?
- progress_pct-Bereiche je Phase: feste Kacheln (0–40 ASR, 40–70 Align, …)
  oder dynamisch aus rtf_learner?
