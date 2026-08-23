# Change 103 — Migrations-Fix: transcriptionrun ohne Settings-Spalten (094-DB)

## Problem

Produktions-Befund 2026-08-23 (App-Start-Fail, ps-webapp-1):

```
sqlite3.OperationalError: no such column: enable_vad
[SQL: INSERT INTO transcriptionrun
  (rec_id, backend, language, enable_vad, enable_diarize, ...)
  SELECT id, ..., enable_vad, ... FROM recording WHERE current_run_id IS NULL]
Application startup failed. Exiting.
```

Die Produktions-DB wurde mit Change 094 erstellt: `transcriptionrun`
existiert dort OHNE die Settings-Spalten (die kamen erst im 099-Modell).
`SQLModel.metadata.create_all` ergänzt existierenden Tabellen KEINE
Spalten → der 099-Backfill (`_backfill_baseline_runs`) referenziert
`enable_vad` etc. im INSERT → Crash beim App-Start → Webapp down.

Der `_drop_legacy_settings_columns`-Guard (`if not drop: return`) greift
hier nicht: Die `recording`-Tabelle hat die Alt-Spalten noch (erster
099-Deploy), also läuft der Backfill — aber die Ziel-Tabelle hat die
Spalten nicht.

## Fix

1. Neuer Helfer `_ensure_run_settings_columns(session)` in db.py: prüft
   `PRAGMA table_info(transcriptionrun)` und ergänzt fehlende Settings-
   Spalten per `ALTER TABLE ... ADD COLUMN` (Typen/Defaults aus dem
   099-Modell: enable_vad 0, enable_noise_reduce 1, enable_enhance 'off',
   übrige NULL/0). Idempotent. Aufgerufen in `_drop_legacy_settings_columns`
   direkt vor `_backfill_baseline_runs` — nur im Migrationspfad (drop nicht
   leer), voll-migrierte DBs bleiben unberührt.
2. DDL-Parser des Table-Rebuilds: Zeilen werden in Spaltendefinitionen
   zerlegt und nur die drop-Spalten entfernt (SQLite hängt per ALTER
   hinzugefügte Spalten in EINER Zeile an die letzte Modell-Spaltenzeile —
   die Zeile komplett zu verwerfen entfernte auch Nicht-drop-Spalten wie
   `current_result_id` und der CREATE scheiterte mit „unknown column in
   foreign key definition“).
3. CI-Flakiness-Fix (TagEditor.test.tsx): „× entfernt Tag → PATCH ohne das
   Tag“ prüfte synchron direkt nach dem Klick — der PATCH feuert
   asynchron und der Test schlug in der CI sporadisch fehl
   („expected vi.fn() to be called at least once“). Assertion auf
   `waitFor` umgestellt.

## Tests

- Integration: tmp-DB im 094-Zustand (recording MIT Alt-Spalten,
  transcriptionrun OHNE Settings-Spalten) + Recording ohne Run →
  `_drop_legacy_settings_columns` läuft ohne Exception; Backfill-Run
  entsteht mit den Settings aus den Alt-Spalten; recording verliert die
  Spalten; transcriptionrun hat sie.
- Idempotenz: zweiter Lauf auf der migrierten DB → kein Crash, keine
  Doppel-Runs.
