# Change 143 — Tasks (Edit-Sync + Queue-Recovery)

## 1. Edit-Sync (Poller-Race)

- [x] `SegmentList.tsx`: Guard `localPendingRef` bleibt bis zur
      Server-Bestätigung gesetzt (kein Auflösen beim propFp-Match)
- [x] `handleSave`: `localPendingRef=false` + `setLocalTexts(null)` NACH
      dem PUT-Erfolg (Server-Wahrheit); Rollback/seq-Konflikt wie gehabt

## 2. Queue-Recovery

- [x] `queue.py`: `_recover_queued()` lädt beim Start DB-Jobs mit
      status='queued' in den Manager (FIFO, Cancel-Guard)
- [x] `recordings.py`: `_abort_queued_run()` — enqueue-Fehler setzen den
      committeten Run auf 'failed' und rollen den Run-Zeiger zurück
      (transcribe + retranscribe)
- [x] `tests/test_queue_recovery.py`: 3 Tests (Recovery lädt queued,
      überspringt processing, Zeiger-Rollback)

## 3. Process-Button

- [x] `useLocale.ts`: `start_btn` → „Process" (de/en/pt) + Tooltips
- [x] `RecordingCard.test.tsx`: Test-Selektor auf „Process"

## 4. Verifikation

- [x] Backend: test_queue_recovery + test_queue_api + test_word_timing
      (27 passed)
- [x] Frontend: 378 Tests, tsc, Build
