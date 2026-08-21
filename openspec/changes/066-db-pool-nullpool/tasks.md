# Change 066 — Tasks

## 1. Fix (`webapp/app/db.py`)

- [x] `from sqlalchemy.pool import NullPool` importieren
- [x] `create_engine(..., poolclass=NullPool)` — SQLite bekommt keine
      künstliche Connection-Obergrenze mehr (QueuePool 5+10 → Timeout)
- [x] WAL-Pragmas + busy_timeout bleiben unverändert (Event-Listener)

## 2. Verifikation

- [x] Smoke: Engine-Pool = NullPool, init_db() + Session-Read ok
- [x] DB-nahe Tests (test_share_link, test_merge_recordings): 13/13 grün
- [ ] Vollsuite `run_full_suite.sh` fail=0 (läuft, nach 065-Suite)

## 3. Abschluss

- [ ] Commit (065 + 066 zusammen) + Push + CI prüfen
- [ ] User informieren: wirkt mit nächstem Deploy (kein Config-Eingriff);
      Ursache (QueuePool-Default auf SQLite) + Fix dokumentiert
