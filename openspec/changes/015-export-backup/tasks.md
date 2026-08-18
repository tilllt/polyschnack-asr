# Change 015 — Tasks

## Phase 1: Encoding-Fix (BOM)

- [ ] 1.1 `routers/recordings.py::download_transcript`: `content.encode("utf-8-sig")`
      für Text-Extensions, `utf-8` für json/jsonl (Helfer `_encode_export`).
- [ ] 1.2 Test: TXT-Download mit Umlauten → Bytes starten mit BOM,
      `Grüße` korrekt als UTF-8; SRT ebenso; JSON ohne BOM.
- [ ] 1.3 Bestehende Export-Tests laufen lassen (Golden byte-gleich —
      nur BOM-Präfix darf sich ändern, Assertions anpassen falls nötig).

## Phase 2: Neue Templates

- [ ] 2.1 `export_templates/csv.json` — `number,start,end,duration,speaker,text` + Header.
- [ ] 2.2 `export_templates/youtube.json` — `mm:ss  text` (Timestamped).
- [ ] 2.3 `export_templates/ass.json` — ASS/SSA mit Style-Header + `[Events]`.
- [ ] 2.4 `export_templates/transcript.json` — `[SPEAKER] text` pro Zeile.
- [ ] 2.5 `export_templates/jsonl.json` — ein JSON-Objekt pro Segment-Zeile.
- [ ] 2.6 `export.py`: optionales `format_paragraph_word` (Word-Level-Loop,
      Fallback Segment-Loop) + `export_templates/srt-words.json`.
- [ ] 2.7 Test: jedes neue Template rendert (Golden-Lines); srt-words mit
      und ohne Words (Fallback).
- [ ] 2.8 Frontend `RecordingCard.tsx`: Dropdown aus `GET /export-templates`
      (Fallback hartkodiert).

## Phase 3: Backup-Export

- [ ] 3.1 Neu `export_backup.py`: `build_backup_zip(rec, versions, tpl_dir)` →
      BytesIO mit transcript.json + audio + txt/srt + manifest.json (SHA-256).
- [ ] 3.2 `GET /recordings/{rid}/backup` (full, done, anon-Limits) —
      Content-Disposition `*-backup-*.zip`.
- [ ] 3.3 Test: Export → ZIP enthält 5 Dateien; manifest-Hashes stimmen;
      transcript.json hat schema_version=1, Segmente inkl. Words, Versionen.

## Phase 4: Backup-Import

- [ ] 4.1 `export_backup.py::import_backup_zip` — manifest-Validierung,
      schema_version-Check, Audio-Extraktion nach `storage_path_for`,
      Recording + TranscriptVersions anlegen (status done).
- [ ] 4.2 `POST /recordings/import-backup` (Multipart, anon-Limits,
      Duplikat-Erkennung content_hash).
- [ ] 4.3 Test: Roundtrip Export→Import → Segmente/Words/Titel identisch,
      Versionszahl identisch; kaputtes Manifest → 400; schema_version 99 → 400.
- [ ] 4.4 Test: anon-Import setzt retention-Metadaten.

## Phase 5: Frontend + Abschluss

- [ ] 5.1 `RecordingCard.tsx`: Dropdown dynamisch + Menüpunkt „Backup (ZIP)".
- [ ] 5.2 `api.ts`: Typ für `/backup` + `/import-backup` (Upload).
- [ ] 5.3 `openspec validate` grün; tsc; vitest; pytest (Change-015-Fälle).
- [ ] 5.4 Commit + Push, CI beobachten (Watchdog), Deploy-Hinweis an User.
