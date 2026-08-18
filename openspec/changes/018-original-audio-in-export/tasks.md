# Tasks

## 1. Original-Audio beim Upload aufbewahren

- [ ] `audio_utils.py`: Helfer `original_path(stored_path, orig_suffix)` →
  `<stored>.orig<orig_suffix>`
- [ ] `recordings.py` `upload_recording`: bei `conv_note` Original-Bytes
  zusätzlich schreiben (Suffix aus `file.filename`)
- [ ] `url_import.py`: gleiche Logik im URL-Import-Flow

## 2. Exporte erweitern

- [ ] `export_backup.py` `build_backup_zip`: `audio.original.<ext>` ins ZIP,
  Manifest deckt ab
- [ ] `account.py` `_zip_recordings`: Original-Datei in den Ordner

## 3. Import bevorzugt Original

- [ ] `export_backup.py` `import_backup_zip`: `audio.original.*` zuerst,
  Fallback `audio.<ext>`; MIME/Dauer aus Original-Suffix

## 4. Tests + CI

- [ ] `test_backup_export.py`: Fall „Original vorhanden" (ZIP enthält beide,
  Manifest valide, Import speichert Original-Suffix)
- [ ] pytest webapp (komplette Suite, ohne test_self_healing) grün
- [ ] Push → Pipeline grün
