# Tasks — Change 099 (immutable Recording-Settings)

- [x] Analyse: Settings-Fluss Upload→Recording→Run→Verarbeitung→API/Backup
- [x] models.py: Settings-Spalten aus `Recording` entfernt, `TranscriptionRun.delivery_target_id`
- [x] db.py: `_drop_legacy_settings_columns` (Backfill + Table-Rebuild) — auf DB-Kopie verifiziert (Spalten weg, Runs/Results, Indizes, idempotent)
- [x] crud.py: `create_recording` ohne Settings, `create_queued_run`, `current_run_for`
- [x] service.py: `process_recording` übernimmt queued-Run + liest Settings im Session-Kontext
- [x] service.py: realign/re-diarize/Delivery aus dem Run (`_current_run`)
- [x] Routen: Upload, transcribe, retranscribe, duplicate, crop, url_import → queued-Runs
- [x] Restore (export_backup) → Run aus dem Manifest
- [x] Leser: ETA (Serialisierung + Reserve), Backup-Manifest, Account-Export → Run
- [x] Test-Migration Kern: test_optin_toggles + test_runs (22/22 grün)
- [ ] Volle Backend-Suite grün
- [ ] OpenSpec spec/tasks committet
- [ ] Commit + Push + CI-Watch
