# Backend & Queue

## Purpose

ASR-Backends registrieren, on demand starten/stoppen (nur Admins), Ressourcen
prüfen, Jobs fair abarbeiten (registrierte User vor anonymen).

## Requirements

### Req 1: Service-Registry

- **Ablauf:** `app/service_registry.py` definiert 5 Backends (parakeet-python,
  pk-cpp, qwen3-asr, ark-asr, voxtral) mit `type` (local/remote), Docker-Image,
  Port, Modell, `cost_per_minute_eur` (Default 0.0) und Kapazität. Validierung
  beim Import (Felder, Kosten ≥ 0).
- **Architektur:** `service_registry.py`, `pricing.py` (is_paid_backend,
  paid_route_for, ensure_free_only).

#### Scenario: Kostenfeld in der Registry

- **Akteure:** Admin.
- **Eingaben:** Registry-Import.
- **Ergebnis:** Jeder Service hat `cost_per_minute_eur ≥ 0`; paid-Backends
  (> 0) werden für anonyme User gesperrt.

### Req 2: Admin-Steuerung über Docker-Socket-Proxy

- **Ablauf:** `POST /api/admin/services/{name}/start|stop|restart` — nur Admins
  (require_admin). Die Webapp spricht NIE direkt den Docker-Socket an, sondern
  `tecriser/docker-socket-proxy` (Container-/Info-Routen + POST, kein
  Exec/Create/Events).
- **Ressourcen-Check vor Start:** RAM/Disk prüfen (VRAM exakt nur bei eigenen
  Servern über deren `/health`); bei Mangel 409 mit Report — kein Startversuch.
- **Stop-Schutz:** Stop nur ohne laufende Jobs auf dem Backend (sonst 409 mit
  Anzahl). Wechsel des Default-Backends startet ein nicht-laufendes Backend
  automatisch (nach Check).
- **Architektur:** `docker_proxy.py` (DockerProxyClient), `routers/admin.py`.

#### Scenario: Stop bei laufenden Jobs

- **Akteure:** Admin.
- **Eingaben:** Stop-Request bei 2 aktiven Jobs.
- **Ergebnis:** 409 mit `{jobs: 2}`; kein Stop.

#### Scenario: Ressourcen-Mangel

- **Akteure:** Admin.
- **Eingaben:** Start bei zu wenig freiem RAM.
- **Ergebnis:** 409 mit Ressourcen-Report; Container startet nicht.

### Req 3: Queue mit Priorität

- **Ablauf:** `QueueManager.enqueue(rec_id, user_id, backend, priority)` —
  `priority=1` für anonyme, `0` für registrierte. Intern PriorityQueue
  (prio, seq, rec_id); `position()` zählt Jobs mit niedrigerer/ gleicher
  Priorität vor sich; `active_jobs_for(backend)` = laufende Jobs.
- **Eingaben:** Nur `/transcribe` und `/retranscribe` erzeugen Jobs.
- **Ergebnis:** Anonyme Jobs laufen **hinter** allen registrierten Jobs
  (auch später eingereihten); FIFO innerhalb gleicher Priorität.
- **Architektur:** `queue.py`; Worker-Threads = Summe der Kapazitäten;
  Re-Enqueue beim Startup aus `crud.list_queued` (mit korrekter Priorität).

#### Scenario: Anon wartet hinter registriertem Job

- **Akteure:** Registrierter User A, anonymer B (gleiches Backend).
- **Eingaben:** A enqueued Job 1 (prio 0), B enqueued Job 2 (prio 1), dann A
  enqueued Job 3 (prio 0).
- **Ergebnis:** Reihenfolge: 1, 3, 2 — B sieht `position=3`.

### Req 4: Queue-API

- **Ablauf:** `GET /api/queue` → eigene Jobs mit `position`, `eta_s`,
  `is_mine` (Position pro Backend); fremde Jobs nur `#id` (anonymisiert).
  `POST /api/queue/{id}/cancel` nur für eigene Jobs.
- **Architektur:** `routers/queue_api.py`.

#### Scenario: Fremde Jobs anonymisiert

- **Akteure:** Registrierter User.
- **Eingaben:** GET /api/queue.
- **Ergebnis:** Eigene Jobs voll; fremde nur `#id` ohne Details.

### Req 5: Paid-Sperre

- **Ablauf:** `ensure_free_only(user, backend, want_llm, llm_mode)` — anonyme
  User dürfen paid-Backends (`cost_per_minute_eur > 0`), LLM-Optimierung und
  LLM-Punctuation nicht nutzen → 403; UI blendet aus.

#### Scenario: Anon + paid-Backend

- **Akteure:** Anonymer User.
- **Eingaben:** Transcribe mit paid-Backend.
- **Ergebnis:** 403 „kostenpflichtige Endpunkte sind für anonyme Nutzung
  gesperrt".
