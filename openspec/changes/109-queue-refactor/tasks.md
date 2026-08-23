# Tasks — Change 109 (Queue-Refactoring)

## Konzept (dieser Change)
- [x] proposal.md: Befunde Q1–Q7 (organisches Wachstum) + Ziel-Architektur J1–J5
- [ ] design.md mit Code-Belegen (queue.py/crud.py/routers/recordings.py/eta.py)
- [ ] Commit + Push
- [ ] Review mit User (Prioritäten, Retry-Politik, SJF-Option)

## Folge-Change (Umsetzung, nach Konzept-OK)
- [ ] Job-Tabelle + Migration (laufende „queued"-Recordings übernehmen)
- [ ] Rehydration beim Start (Zombie-Fix) + Restart-Markierung für running
- [ ] Retry/Backoff/Dead-Letter + Admin-Retry-API
- [ ] ETA zentralisieren (eine Funktion, drei Aufrufer auf einen Stand)
- [ ] Recording.status ableiten (ein Status-System)
- [ ] Prioritätsstufen (admin/user/anon) + optionale SJF
- [ ] Queue-Admin-UI (Jobs, Retry, Priorität)

## Sofort-Fix (unabhängig, niedrig hängend)
- [ ] Zombie-Schutz minimal: beim Start `status="queued"`-Recordings, die nicht
      in der RAM-Queue sind, auf `failed` mit Grund „Server-Neustart" setzen
      (oder re-enqueuen — Entscheidung im Konzept-Review)
