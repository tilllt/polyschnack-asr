# Tasks — Change 023 (Self-Healing)

## Phase 0 — Dokumentation
- [x] proposal.md: Verhaltens-Delta (audio_missing, 410, Sweep, Export)
- [x] specs/transcription/spec.md (ADDED Requirement)
- [ ] OpenSpec-validieren

## Phase 1 — Backend (umgesetzt 18.08., aus WIP 15.08. fertiggestellt)
- [x] `_audio_file_exists` + `_ensure_audio_present` (410 „audio file
      missing") in `routers/recordings.py`
- [x] `audio_missing`-Flag in `_recording_to_dict`
- [x] Guard in `transcribe_ep` (410 statt 500)
- [x] `duplicate_recording`: 410 statt 409
- [x] Delete funktioniert trotz fehlender Datei (Bestand)
- [x] `orphan_sweep.py`: sweep_orphan_files (min_age, dry_run) +
      collect_referenced_paths (Bestand aus WIP)
- [x] Admin-Trigger `POST /api/admin/self-heal` (dry_run-Default)
- [x] `account.py` (Account-Export-ZIP, AUDIO_FEHLT.txt statt Crash)
      + Router in `main.py` registriert (`/api/account/export`)
- [x] Tests `test_self_healing.py`: 10/10 grün

## Phase 2 — Abschluss
- [x] Sanity: Routen registriert, main.py-Import sauber
- [ ] Vollsuite (Regression), Commit + Push, CI prüfen
- [ ] GUI: Defekt-Badge nutzt `audio_missing` (Folge-Change, Frontend)
