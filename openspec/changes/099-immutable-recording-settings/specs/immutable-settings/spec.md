# Spec — Settings leben nur noch im TranscriptionRun

## Datenmodell
- `Recording`: KEINE Settings-Spalten mehr (Migration entfernt: `enable_*`,
  `diarize_*`, `prompt_template_id`, `delivery_target_id`, `llm_endpoint_id`).
  `backend`/`language` bleiben (Betrieb/Ergebnis-Metadaten).
- `TranscriptionRun` trägt ALLE Settings (inkl. neuem `delivery_target_id`).

## Schreibpfade (Settings → Run)
| Aktion | Run |
|---|---|
| Upload / URL-Import | neuer `queued`-Run (Form-Settings) |
| transcribe | ältesten `queued`-Run übernehmen + Body-Overrides; sonst neuer Run |
| retranscribe | IMMER neuer Run |
| duplicate / crop (transcribe-range) | neuer Run, Settings aus `current_run` des Originals |
| Backup-Restore | neuer Run aus dem Manifest |

`current_run_id` zeigt auf den zuletzt angelegten/übernommenen Run.

## Lesepfade (Settings aus dem Run)
- `process_recording`: übernimmt ältesten `queued`-Run (Fallback: `current_run_id`,
  sonst neuer Default-Run), liest Settings INNERHALB der Session (Detached-Falle)
- realign / re-diarize: `current_run` (Fallback jüngster Run) via `_current_run`
- ETA (Serialisierung + `set_processing`-Reserve), Backup-Manifest,
  Account-Export, API-Serialisierung (`enable_*`-Felder bleiben im Payload,
  aus dem Run) — Fallback Defaults wenn kein Run

## Migration (Startup, idempotent)
1. Backfill: Recordings ohne Run → Baseline-Run (`done` + Result bei Text,
   sonst `queued`) aus den Alt-Spalten
2. Table-Rebuild (`recording_099`): DDL aus `sqlite_master` bereinigt
   (Spalten- + FK-Zeilen der Settings), Daten-Kopie, RENAME, Indizes neu
3. Nur wenn Alt-Spalten existieren; zweiter Lauf = no-op

## Frontend
Keine Änderung: API-Payload-Form (`enable_*`-Felder) bleibt unverändert.

## Fallback-Defaults (kein Run)
`enable_vad/diarize/streaming/punctuation/llm_enhance=False`,
`enable_noise_reduce=True`, `enable_enhance="off"`, IDs `None`.
