# Change 028 — Tasks

## Fix
- [ ] `recording_health.py:127` — Logging robust: `(b[0].uid or "?")[:8]`
- [ ] Regressionstest (Recording ohne uid + fehlende Datei → kein Crash,
      1 Update) in `test_change014_storage_health_title.py`
- [ ] Webapp-Tests grün
- [ ] Commit + Push, CI prüfen und melden
