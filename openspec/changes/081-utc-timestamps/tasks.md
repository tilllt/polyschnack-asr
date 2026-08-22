# Tasks — Change 081

- [ ] T1: `webapp/app/timeutil.py` mit `iso_utc()` anlegen
- [ ] T2: 16 `.isoformat()`-Stellen in 6 Routern auf `iso_utc()` umstellen
      (account, annotations, keys, recordings, shares, versions)
- [ ] T3: Backend-Unit-Tests für `iso_utc` (naiv/aware/None)
- [ ] T4: Frontend: `parseUtcMs`-Helper + `secondsSince`/`fmtDate`/`fmtHHMM`
- [ ] T5: Frontend-Test: naive vs. `Z`-String identisch (TZ-invariant)
- [ ] T6: Vollsuite (Backend + Frontend), Commit, Push, CI-Check
