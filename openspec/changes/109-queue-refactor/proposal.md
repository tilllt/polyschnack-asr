# Change 109 — Queue-Refactoring: persistenter Job-Runner statt organisch gewachsener FIFO

> Status: KONZEPT (Anmerkung Ruben, 23.08.2026: „das Queuing ist insgesamt im negativen Sinne organisch gewachsen").
> Design-Change: Analyse + Ziel-Architektur; Umsetzung als Folge-Change.

## Problem

Das Queuing ist über viele Changes gewachsen und hat strukturelle Schwächen,
die zu hängenden Jobs, unehrlichen Stati und doppelter Logik führen:

1. **In-Memory-Queue ohne Rehydration → Zombie-Jobs.**
   Die Queue lebt ausschließlich im RAM (`queue.py` `QueueManager._jobs`).
   Beim Webapp-Neustart ist sie leer, aber die DB-Recordings bleiben für immer
   `status="queued"` (gesetzt via `crud.set_queued`). Es gibt KEINE
   Rehydration: `crud.select_queued` (crud.py Z. 329) existiert, wird aber von
   der Queue nicht genutzt. Folge: Jobs, die beim Restart verloren gehen,
   bleiben ewig „in der Warteschlange" (UI lügt), Re-Transcribe blockiert.
2. **Zwei parallele Status-Systeme.**
   `Recording.status` (uploaded|queued|processing|done|failed, models.py Z. 43)
   UND `TranscriptionRun.status` (queued|processing|done|failed, Z. 207) werden
   parallel gepflegt — die Queue schreibt Recording.status
   (`crud.set_queued/set_processing/…`), der Run dokumentiert die Ausführung.
   Welcher Status ist die Wahrheit? Jede Desynchronisation erzeugt ehrliche-
   Status-Fehler (UI zeigt „queued" obwohl nichts läuft).
3. **ETA/Position an drei Stellen berechnet.**
   (a) `queue.py list()` (Z. 201–221, avg_ms × position), (b) Router
   `routers/recordings.py` `_queue_position_for`/`_queue_eta_s_for`
   (Z. 504–515), (c) `eta.py` mit Overhead-Konstanten
   (VAD/NOISE_REDUCE/ENHANCE/PUNCT/SEP) + statischer Schätzung + Learner
   (avg_recent_processing_ms). Drei Quellen, die auseinanderlaufen können.
4. **Kein Retry, kein Dead-Letter.**
   `_worker_loop` (queue.py Z. 265–266): Exception → nur log; der Job
   verschwindet aus `_jobs`, das Recording bleibt evtl. `processing`/`failed`
   ohne Grund. Kein Retry mit Backoff, kein Dead-Letter-Workflow, kein
   Admin-Retry außer manuellem Re-Transcribe.
5. **Thread-Ökosysteme statt eines Job-Runners.**
   Nebenläufigkeit an vielen Stellen: QueueManager-Worker, retention-sweep
   (main.py Z. 174), peaks-backfill (Z. 193), yjs (Z. 203), dazu eigene
   Threads in service.py (align-heartbeat, diar, peaks). Kein einheitliches
   Muster für Jobs/Lebenszyklus/Fehler.
6. **Priorität/Fairness rudimentär.**
   Nur zwei Stufen (0 = registriert, 1 = anonym, spec backend-queue); ein
   90-min-Job blockiert ein Backend-Semaphore lange; kein SJF, keine
   Admin-Priorität, keine per-Job-Deadline.
7. **Settings-Verteilung über drei Ebenen.**
   Settings im TranscriptionRun (Change 099) + Recording-Flags + globale
   Defaults — der Job transportiert Settings implizit; bei neuen Stufen
   (separate/align) wächst das weiter (Change 106/108).

## Ziel-Architektur

### J1. Persistente Job-Tabelle als einzige Wahrheit
```
Job = { id, rec_id, run_id, backend, status: queued|running|done|failed|cancelled,
        priority: 0=admin,1=user,2=anon, attempts, max_attempts,
        timeout_s, error, created_at, started_at, finished_at,
        settings_snapshot: JSON }        // Settings-Foto zum Enqueue-Zeitpunkt
```
- Queue = SELECT WHERE status='queued' ORDER BY priority, created_at.
- **Rehydration beim Start:** `queued`-Jobs werden wieder eingereiht;
  `running`-Jobs (Restart während der Verarbeitung) werden als `failed`
  markiert („abgebrochen durch Neustart") mit Admin-Hinweis — nie still
  hängen lassen.
- `Recording.status` wird zum abgeleiteten Feld (View über aktiven Job);
  `TranscriptionRun` bleibt die Ausführungs-Doku (ehrlicher Pfad).

### J2. Ein Worker-Loop, ein Fehlermodell
- Retry: transienter Fehler → `attempts+1`, Backoff (2^attempts × 5 s, max 3);
  danach `failed` mit `error`-Detail (Change-101-Muster: ehrlicher Grund).
- Timeout pro Job-Typ (ASR 3600 s, align 900 s, separate …) statt eines
  globalen `_max_processing_s`.
- Dead-Letter: `failed`-Jobs mit `error` im Admin-Queue-View, Aktionen
  „Erneut einreihen" / „Als failed bestätigen".
- Cancel: `cancel_requested` (bestehendes Muster) bleibt, aber persistiert
  (Restart während Cancel → Job wird beim Start ehrlich `cancelled`).

### J3. Eine ETA-Quelle
- `eta.py` wird die EINZIGE Schätzfunktion: `estimate_job_s(settings)` (Statik +
  Learner) × Position (aus der Job-Tabelle) + Overheads. Router und
  `queue.list()` rufen dieselbe Funktion; keine Router-eigene Rechnung.
- Learner-Daten (avg_recent_processing_ms) bleiben, aber pro Backend gewichtet.

### J4. Fairness
- Drei Prioritätsstufen (admin/user/anon), FIFO innerhalb; optional SJF-Hint
  (kurze Jobs zuerst bei gleicher Priorität) als Admin-Flag.
- Backend-Kapazität weiter über Semaphore/`concurrency` aus der
  Service-Registry; aber das Queue-Objekt ist die Job-Tabelle (kein RAM-Dict).

### J5. Queue-API/UI
- `GET /api/queue` (Admin: alle Jobs mit rec_id/status/priority/attempts/error;
  User: nur eigene, anonymisiert — bestehendes Verhalten).
- `POST /api/queue/{job_id}/retry` (Admin), `DELETE` (cancel), `PATCH priority`.

## Verifikation

- Restart-Test: 3 queued + 1 running Job → Webapp-Neustart → queued laufen
  weiter, running ehrlich `failed` (Grund „Neustart").
- Retry-Test: Backend-Fehler beim 1. Versuch → 2. Versuch läuft; 3× Fehler →
  `failed` mit letztem Fehler.
- ETA-Konsistenz: `/api/recordings` (queue_eta_s) == `/api/queue` (eta_s) ==
  eta.py-Ausgabe für denselben Job.
- Fairness: 1 Admin- + 1 User- + 1 Anon-Job gleichzeitig → Reihenfolge
  admin → user → anon.
- Kein Zombie: nach Restart zeigt die UI nie „queued" für einen Job, der
  nicht mehr in der Tabelle steht.
