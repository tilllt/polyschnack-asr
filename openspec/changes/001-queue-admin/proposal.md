# Change Proposal 001 — Queue, Backend-Verwaltung & Admin

**Status:** Implemented (retroaktiv)

## Why
- On-demand-Steuerung der ASR-Container ohne direkten Docker-Socket-Zugriff.
- Faire Verteilung: registrierte User vor anonymen; Queue-Gesamtbild in der UI.

## What
- Service-Registry mit 5 Backends (Kostenfeld `cost_per_minute_eur`).
- Admin-Router (`/api/admin/*`) mit `require_admin` (Env-Admins + Gruppen).
- Docker-Socket-Proxy-Client; Ressourcen-Check vor Start; Stop-Schutz.
- Thread-Queue mit `priority` (0 registriert / 1 anonym), `position()`,
  `active_jobs_for()`; Re-Enqueue im Startup.
- Queue-API mit Position/ETA, fremde Jobs anonymisiert (#id), Cancel nur eigene.

## Changes
- Neu: `service_registry.py`, `docker_proxy.py`, `routers/queue_api.py`,
  `deps.py`, `queue.py` (Prioritäts-Erweiterung), Tests `test_queue*.py`,
  `test_admin_role.py`.
- Geändert: `routers/recordings.py` (enqueue mit priority),
  `main.py` (Startup-Re-Enqueue).

## Downgrade
- Priorität entfernen → `queue.Queue` + FIFO; Admin-Router ohne require_admin.
