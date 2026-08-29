# Change 155 — Universelles Scheduling: Umsetzung 109/110 (Gap-Analyse + Schritte 1+4)

**Status:** Proposed (Schritt 1 + Schritt 4 umgesetzt)

## Gap-Analyse (2026-08-29): Alle Programmteile vs. universelles Scheduling

### Erfasst im QueueManager (queue.py)
Upload-/Transcribe-/Retranscribe-Jobs — 3 enqueue-Aufrufer:
`main.py:111` (Upload), `routers/recordings.py:1812` (transcribe),
`routers/recordings.py:1942` (retranscribe). FIFO + Semaphore pro Backend,
Cancel (queued+processing), Job-Timeout, Priorität 0/1, Rehydration nur
`queued` (Change 143).

### NICHT erfasst (Gaps) — fire-and-forget-Threads / Scheduled-Tasks / Router-Threads
1. `service.py:1599` + `:2577` — `_run_background_align` (nach done / alignment_pending) — **SEIT SCHRITT 4 ALS QUEUE-JOB**
2. `service.py:1666` — `_run_background_rediarize` — **SEIT SCHRITT 4 ALS QUEUE-JOB**
3. `service.py:1125/1910/1950` — 3 Heartbeat-Thread-Kopien (`align-hb-*`,
   `heartbeat-*`, `job-heartbeat-*`)
4. `diarize.py:162` — `_poll_progress` (Diarization-Progress)
5. `main.py:174/193` — `_sweep_loop` (retention), `_peaks_loop` (peaks-backfill)
6. `routers/recordings.py:421` — `_compute_peaks_background` (Upload)
7. `routers/models.py:288` — `_download_vad` (VAD-Modell)
8. `yjs/rooms.py:174` — `asyncio.create_task` (yjs-Server)

### Fehlende Kernstücke (Change 109 Folge-Change)
- Job-Tabelle in der DB (Jobs leben nur im RAM-Dict `QueueManager._jobs`)
- ~~Rehydration deckt nur `status="queued"`~~ — **erledigt:** `processing`-Zombies
  (heartbeat-basiert, nur wenn sicher tot) + align/rediarize-Statusfelder werden rehydriert
- Retry/Backoff/Dead-Letter + Admin-Retry-API
- ETA zentralisieren (eine Funktion, drei Aufrufer)
- Recording.status ableiten (ein Status-System)
- Queue-Admin-UI

## Umsetzungsschritte (Reihenfolge)
1. [x] **Zombie-Fix**: `_recover_queued` nimmt auch `processing`-Recordings
       auf und re-enqueued sie (set_queued — konsistenter Zustand,
       frischer Heartbeat). User-Befund 2026-08-29: Deploy während
       Verarbeitung → Job weg, Status ewig processing.
2. [ ] Job-Tabelle (Runs werden Jobs) + Rehydration aus Tabelle
3. [ ] `run_workflow` — process_recording in Phasen zerlegen (Change 110)
4. [x] **align/rediarize als Queue-Jobs** (nackte Threads entfernt):
       Job.kind + payload, Job-Key (int für transcribe, `align-{id}`/
       `rediarize-{id}`), kind-Dispatch im Worker (set_processing nur für
       transcribe — schützt text/segments), `run_align_job`/
       `run_rediarize_job` mit Selbst-Vorbereitung des Audios
       (`_prepare_align_audio`, VAD/enhance/separate aus den Run-Settings —
       reproduzierbare Zeitbasis, rehydrierbar), Schedules → enqueue.
       Design-Hinweis: align/rediarize belegen einen Backend-Slot
       (Semaphore) — ein langes rediarize lässt Transkriptionen auf dem
       selben Backend warten (Preis des universellen Schedulings).
5. [ ] Heartbeat-Muster vereinheitlichen (3 Kopien → 1)
6. [ ] SCHEDULED_TASKS-Registry (sweep/peaks/health) + Router-Threads raus
7. [ ] Grep-Gate in CI (keine nackten Threads in service.py)
