# Change Proposal 015 — Export-Härtung: UTF-8-BOM, mehr SubtitleEdit-Templates, Backup-ZIP mit Import

**Status:** Proposed

## Why

Drei User-Befunde (2026-08-18):

1. **Encoding-Regression „nur-text":** Der TXT-Download zeigt wieder
   Sonderzeichen statt Umlauten. Der Backend-Header `charset=utf-8` ist
   vorhanden, reicht aber nicht: Der Browser speichert die Datei als
   UTF-8 **ohne BOM**, und Windows-Editoren (Notepad < 1903, Excel,
   viele Text-Tools) raten dann Latin-1/ANSI → „ä/ö/ü/ß" werden zu
   „Ã¤"-Artefakten. Der frühere Fix (`8062a5c`) hat den Template-Refactor
   überlebt, aber das Problem ist aus Sicht der Ziel-Editoren nicht gelöst.

2. **Nur drei Exportformate:** Eingebaut sind `txt|srt|vtt`. Gebräuchliche
   Formate fehlen: CSV für Excel, YouTube-Stil-Timestamps, ASS/SSA
   (Advanced SubStation), Sprecher-Transcript, JSON-Lines, Word-Level-SRT.
   Die Template-Infrastruktur (Change 008) kann das ohne Code-Änderung —
   es fehlen nur die Template-Dateien.

3. **Kein vollständiger Backup:** Es gibt keinen Export, der die komplette
   Transkription (Text, Word-Timings, Segment-Timings, Versionen,
   Einstellungen) zusammen mit dem Original-Audio als eine Datei liefert
   und wieder importierbar ist. User-Frage: „Können wir eine Art Backup
   einbauen, der die komplette Transkription so exportiert, dass man sie
   wieder in PolySchnack importieren kann? … die Infos aus der Datenbank
   (Transkriptionstext, Word Timing, segment Timing usw.) in die bereits
   existierende sidecar json schreiben, plus das ursprüngliche audio File,
   finale Ausgabe als ZIP zum Download." — **Ja, das Konzept macht Sinn.**

## What

Drei Verhaltensänderungen:

1. **Encoding-Härtung:** Text-Exporte (alle Template-Formate mit
   Text-Extension: txt, srt, vtt, csv, ass, …) werden als **UTF-8 mit BOM**
   (`utf-8-sig`) ausgeliefert. Notepad, Excel und andere Windows-Editoren
   erkennen das Encoding damit zuverlässig. Maschinenlesbare Formate
   (json, jsonl) bleiben BOM-frei (reines UTF-8). Der `charset=utf-8`-
   Content-Type bleibt bestehen.

2. **Mehr Standard-Templates (SubtitleEdit-kompatibel, dateibasiert):**
   - `csv` — Excel-tauglich: `number,start,end,duration,speaker,text` (CSV-escaped)
   - `youtube` — Timestamped Transcript im YouTube-Stil: `mm:ss  Text`
   - `ass` — Advanced SubStation Alpha (mit Style-Header, `[Events]`)
   - `transcript` — Sprecher-Transcript: `[SPEAKER_01] Text` pro Zeile
   - `jsonl` — JSON Lines, ein Segment-Objekt pro Zeile (maschinenlesbar)
   - `srt-words` — Word-Level-SRT: pro Wort ein Cue (wenn Word-Timings
     vorhanden sind; neues optionales Template-Feld `format_paragraph_word`,
     Fallback auf Segment-Cues wenn keine Words)
   Das UI-Dropdown wird dynamisch aus `GET /export-templates` befüllt
   (statt hartkodiert `txt|srt|vtt`).

3. **Backup-Roundtrip (Export + Import):**
   - **Export:** `GET /recordings/{rid}/backup` → ZIP mit:
     - `transcript.json` — kanonisches, versioniertes Backup-Schema
       (`schema_version: 1`): Metadaten (Titel, Dateiname, App-Version,
       Export-Zeitpunkt), Einstellungen (alle Recording-Toggles), Volltext,
       Segmente **inkl. Word-Timings**, und die **Transkript-Versionen**
       (aus `TranscriptVersion`, für Diff/Restore nach Import).
     - `audio.<ext>` — das Original-Audio (Kopie von `stored_path`).
     - `transcript.txt` + `transcript.srt` — Lese-Ausgabe (Bonus).
     - `manifest.json` — SHA-256-Hash je Datei (Integritätsprüfung nach
       Transfer, Basis für den Import).
   - **Import:** `POST /recordings/import-backup` (Multipart-ZIP) →
     validiert `manifest.json` (Hash-Prüfung) und `schema_version`
     (unbekannte Version → 400 mit klarer Meldung), legt ein neues
     Recording mit Status `done` an: Audio wird in den User-Ordner
     kopiert, Titel/Segmente/Words/Einstellungen werden übernommen,
     Versionen werden als `TranscriptVersion`-Snapshots wiederhergestellt.
     Keine Neu-Transkription nötig.
   - **Datenschutz (anon):** Backups anonym erzeugter Recordings enthalten
     keine DB-internen IDs (nur eine Export-UUID); `retention_minutes`
     wird im JSON vermerkt. Import als anon-User unterliegt der normalen
     Retention (Countdown startet beim Import).
   - **Schema-Versionierung:** `schema_version` im `transcript.json`;
     Import akzeptiert nur kompatible Versionen (aktuell 1). Zukünftige
     Erweiterungen erhöhen die Version, Altexporte bleiben lesbar.

## Changes

- `routers/recordings.py`: `download_transcript` — Response-Encoding auf
  `utf-8-sig` für Text-Extensions (BOM), unverändert für json/jsonl.
- `app/export_templates/`: neue Template-Dateien `csv.json`, `youtube.json`,
  `ass.json`, `transcript.json`, `jsonl.json`, `srt-words.json`.
- `export.py`: optionales Feld `format_paragraph_word` (Word-Level-Loop,
  nur wenn Words vorhanden; sonst Segment-Loop).
- Neu `export_backup.py`: `build_backup_zip(rec, …)` + `import_backup_zip`
  (Schema v1, Manifest-Prüfung, Versions-Wiederherstellung).
- `routers/recordings.py` (+ neu `routers/backup.py`): Endpoints
  `GET /recordings/{rid}/backup`, `POST /recordings/import-backup`,
  Access-Checks wie Download (`full`), anon-Limits.
- Frontend `RecordingCard.tsx`: Dropdown-Formate dynamisch aus
  `/export-templates`; Menüpunkt „Backup (ZIP)".
- Tests: Encoding-BOM (txt/srt mit Umlauten), neue Templates
  (Golden-Ausgaben), Backup-Roundtrip (Export → Import → byte-gleiche
  Segmente/Words, Hash-Prüfung, schema_version-Fehler → 400).

## Downgrade

- BOM: einzeilig zurück auf `utf-8` (nur Text-Downloads betroffen, kein
  Datenverlust — BOM ist ein Präfix von 3 Bytes).
- Templates: JSON-Dateien entfernen; Dropdown fällt auf die harten
  `txt|srt|vtt` zurück.
- Backup: Endpoints + Modul entfernen; ZIP-Dateien bleiben lesbar
  (manifest.json + transcript.json sind plain JSON, kein Lock-in).

## Specs-Delta

- MODIFIED: `specs/transcription/spec.md` (Req 6 Export: BOM-Encoding +
  dynamische Templates; Req 7 neu: Backup & Restore)
