# Tasks — Change 047: Job-weiter Heartbeat

## Task 1: Implementierung

- [ ] `_start_job_heartbeat(rec_id, interval_s=5.0)` in service.py
      (tickt last_heartbeat_at via set_progress mit note=None)
- [ ] Start in `process_recording` direkt nach read_bytes
- [ ] Stopp im finally (done/failed)
- [ ] `hb_job`-Init vor dem try (None)

## Task 2: Tests

- [ ] Job-Heartbeat tickt last_heartbeat_at (Fake-Session)
- [ ] Stoppt auf Event (kein Ticken nach set())
- [ ] Ändert NICHT progress_note/phase_started_at (note=None-Guard)
- [ ] Alle bestehenden Heartbeat-Tests grün
- [ ] Backend-Tests gesamt grün

## Task 3: Commit + Push

- [ ] Commit mit Change-047-Referenz
- [ ] CI prüfen und melden
