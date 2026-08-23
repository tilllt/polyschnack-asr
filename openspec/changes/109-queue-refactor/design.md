# Change 109 — Design: Queue-Befunde mit Beleg

Ergänzt proposal.md. Stand 23.08.2026, Repo-Stand main @ 8a94d21.

## Befund-Katalog

**Q1. In-Memory-Queue ohne Rehydration (Zombie-Jobs).**
- `queue.py` Z. 77: `self._jobs: Dict[int, Job]` — die gesamte Queue lebt im RAM.
- `enqueue` (Z. 122–139) schreibt nur `_jobs` + `crud.set_queued` (DB-Status).
- **Kein** Rehydrate-Aufruf in `queue.py`/`main.py`; `crud.select_queued`
  (crud.py Z. 329: `select(Recording).where(Recording.status == "queued")`)
  wird von der Queue **nicht** genutzt — Überbleibsel, das auf eine geplante
  Rehydration hindeutet.
- Folge: Webapp-Restart → alle queued-Recordings bleiben für immer „queued"
  (UI lügt), werden nie verarbeitet.

**Q2. Zwei parallele Status-Systeme.**
- `models.py` Z. 43: `Recording.status` (uploaded|queued|processing|done|failed).
- `models.py` Z. 207: `TranscriptionRun.status` (queued|processing|done|failed).
- Die Queue pflegt `Recording.status` (crud.set_queued/set_processing/set_done/
  set_failed), der Run ist die Ausführungs-Doku — wer ist die Wahrheit? Kein
  Constraint hält beide synchron.

**Q3. ETA/Position an drei Stellen.**
- `queue.py list()` Z. 206–218: `eta_s = position × avg_ms/1000`
  (avg_recent_processing_ms).
- `routers/recordings.py` Z. 504–515: eigene `_queue_position_for`/
  `_queue_eta_s_for` — zweite Berechnung, in der Recording-Liste.
- `eta.py`: Overhead-Konstanten (VAD/NOISE_REDUCE/ENHANCE/PUNCT/SEP) +
  statische Schätzung + Learner — dritte Quelle, andere Basis
  (job-spezifische Settings statt Queue-Durchschnitt).
- Drei Schätzungen für „wie lange dauert es" — keine Garantie der Konsistenz.

**Q4. Kein Retry/Dead-Letter.**
- `queue.py` `_worker_loop` Z. 265–266: `except Exception: log.exception(...)`
  — der Job wird aus `_jobs` entfernt (Z. 270), das Recording bleibt in dem
  Status, den `process_recording` zuletzt setzte; kein automatischer Retry,
  kein Dead-Letter, keine Admin-Aktion außer manuellem Re-Transcribe.

**Q5. Thread-Ökosysteme statt eines Job-Runners.**
- `main.py` Z. 174 (retention-sweep), Z. 193 (peaks-backfill), Z. 203 (yjs),
  dazu QueueManager-Worker (queue.py Z. 101–108) und service.py-eigene Threads
  (Z. 706 align-heartbeat, Z. 1097/1158 diar/peaks, Z. 1357/1397/1956).
- Sechs+ parallele daemon-Thread-Patterns mit je eigener
  Fehler-/Lebenszyklus-Logik — das „organische Wachstum" von Ruben.

**Q6. Priorität/Fairness rudimentär.**
- `queue.py` `enqueue` Z. 122–139: `priority` (0/1) nur aus User-Typ
  (registriert/anonym, spec backend-queue Req 3). `sem.acquire()` (Z. 246–247)
  ohne Deadline — ein 90-min-Job blockiert ein Backend-Semaphore; kein SJF,
  keine Admin-Priorität.

**Q7. Settings über drei Ebenen verteilt.**
- Settings im `TranscriptionRun` (Change 099) + Recording-Flags
  (enable_vad/diarize/…) + globale Defaults — der Job transportiert Settings
  nur implizit über rec_id; Change 106/108 (separate, reprocess-Bereiche)
  erhöhen die Zahl der Settings weiter.

## Verknüpfung mit Change 108

- 109 (Queue) ist die **Ausführungs-Schicht** für 108s Re-Prozess-Pipeline:
  `reprocess`-Aufträge (align/diarize/asr-Bereich) laufen als Jobs desselben
  Job-Runners (J1) — Bereiche + steps im `settings_snapshot`.
- Der ehrliche Status-Pfad (Change 095/101) wird durch J2 (Retry/Dead-Letter
  mit Grund) und die Rehydration (Q1) komplettiert.
