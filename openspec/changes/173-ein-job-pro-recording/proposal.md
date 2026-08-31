# Change 173 — max. ein Job pro Recording (keine parallelen Aufträge)

**Status:** Proposed

## Befund (2026-08-31, Live: Recording 49b7b10a)

Re-transcribe + Re-align konnten parallel gestartet werden: Die Queue-
Keys unterscheiden sich (transcribe=rec_id, align=align-{rec_id},
rediarize=rediarize-{rec_id}) → der alte Guard (nur gleicher Key) griff
nicht. Zwischen Enqueue und Worker-Start bleibt rec.status="done" → auch
der Status-Guard („Transkription ist noch nicht fertig") griff nicht.

Folge (beobachtet): re-transcribe lief mit htdemucs-Separation, der
parallel gestartete re-align bekam vom crispr-sep einen 409 (ein Job
gleichzeitig), fiel aufs Original-Audio zurück und skipped.

## Lösung

`JobQueue.enqueue` lehnt jeden Job ab, sobald für DIESE Recording bereits
ein Job aktiv ist (queued/processing) — unabhängig vom Key. Die Routen
mappen QueueError bereits auf 409 mit klarer Meldung.

## Betroffene Dateien

- `webapp/app/queue.py`
- `webapp/tests/test_queue_single_job.py` (neu)
