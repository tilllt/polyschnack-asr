# Change 028 — Design

## Ursache

`scan_broken_recordings` liefert `(rec, reason)`-Tupel; `rec` ist immer
eine Recording-Instanz (DB), aber `rec.uid` kann bei Legacy-Datensätzen
`None` sein (nullable Spalte aus der Zeit vor der uid-Einführung).
`run_health_scan` loggt `b[0].uid[:8]` → `None[:8]` → TypeError.

## Fix

`webapp/app/recording_health.py`, Zeile 127 — robustes Logging:

```python
names = ", ".join((b[0].uid or "?")[:8] for b in broken[:5])
```

`uid=None` → `"?"` im Log; Datensatz wird weiterhin von `mark_broken`
als `failed` markiert (unverändert).

## Regressionstest

`webapp/tests/test_change014_storage_health_title.py` ergänzen:
Recording mit `uid=None`, `stored_path` auf nicht-existenten Pfad,
`created_at` alt, Status `done` → `run_health_scan` wirft keine
Exception und liefert 1 (markiert als failed).

## Kein Scope

- Keine Migration/Backfill der uid-Nulls (separater Change, falls
  gewünscht).
