## MODIFIED Requirements

### Requirement: Export (Encoding-Härtung + dynamische Templates)

- **Ablauf:** `GET /api/recordings/{rid}/download?format=<template>`.
  `format` ist ein Template-Name aus `DATA_DIR/export_templates/*.json`;
  eingebaut: `txt|srt|vtt|csv|youtube|ass|transcript|jsonl|srt-words`.
  `GET /api/export-templates` listet Name+Endung aller verfügbaren
  Templates; das UI-Dropdown wird daraus befüllt (keine hartkodierte
  Formatliste). `max_duration_s` (optional): Re-Segmentierung vor dem
  Export — identisch zur Preview in der Transkriptionsansicht.
- **Encoding:** Text-Formate (txt, srt, vtt, csv, ass, transcript,
  youtube) werden als **UTF-8 mit BOM** (`utf-8-sig`) ausgeliefert —
  Windows-Editoren (Notepad, Excel) erkennen Umlaute damit zuverlässig.
  Maschinenlesbare Formate (json, jsonl) bleiben reines UTF-8 ohne BOM.
  `charset=utf-8` im Content-Type bleibt bestehen.
- **Word-Level-SRT:** Das Template `srt-words` nutzt ein neues optionales
  Template-Feld `format_paragraph_word`: wenn Segmente Word-Timings
  (`words[]` mit start/end/text) enthalten, wird pro Wort ein Cue
  gerendert; ohne Words fällt der Renderer auf den Segment-Loop zurück
  (identische Ausgabe wie `srt`).
- **Ausgaben:** Download-Datei mit `Content-Disposition: attachment`.
- **Architektur:** `app/export.py` (Template-Renderer, Change 008),
  `app/routers/recordings.py::download_transcript`.

#### Scenario: Untertitel exportieren

- **Akteure:** Beliebig mit Zugriff.
- **Eingaben:** `download?format=srt`.
- **Ausgaben:** SRT-Datei mit Segment-Timestamps, UTF-8 mit BOM.

#### Scenario: Umlaute im TXT-Download

- **Akteure:** Beliebig mit Zugriff.
- **Eingaben:** `download?format=txt` bei einer Aufnahme mit „Grüße aus Köln".
- **Ausgaben:** Bytes beginnen mit `EF BB BF` (BOM); „Grüße" liegt als
  korrekte UTF-8-Sequenz vor — Notepad/Excel zeigen die Umlaute korrekt.

#### Scenario: Word-Level-SRT

- **Akteure:** Besitzer.
- **Eingaben:** `download?format=srt-words` bei Segmenten mit Word-Timings.
- **Ausgaben:** Ein SRT-Cue pro Wort (Nummer, Start/End, Wort). Ohne
  Word-Timings: Fallback auf Segment-Cues (gleiche Ausgabe wie srt).

### Requirement: Standard-Templates erweitert

- **Ablauf:** Sechs neue Template-Dateien in `app/export_templates/`
  (werden beim Start nach `DATA_DIR/export_templates/` kopiert):
  `csv.json` (Excel: `number,start,end,duration,speaker,text`, Header-Zeile),
  `youtube.json` (Timestamped im YouTube-Stil: `mm:ss  Text`),
  `ass.json` (Advanced SubStation Alpha inkl. Style-Header + `[Events]`),
  `transcript.json` (Sprecher-Transcript: `[SPEAKER_01] Text` pro Zeile),
  `jsonl.json` (JSON Lines: ein Segment-Objekt pro Zeile),
  `srt-words.json` (Word-Level, s. o.).
- **Erweiterbarkeit:** Neue Formate bleiben dateibasiert (Template-JSON,
  kein Code); die bestehende SubtitleEdit-Platzhalter-Syntax (Change 008)
  gilt unverändert.

#### Scenario: CSV-Export in Excel

- **Akteure:** Besitzer.
- **Eingaben:** `download?format=csv`.
- **Ausgaben:** CSV mit Header `number,start,end,duration,speaker,text`,
  Textfelder korrekt CSV-escaped; Excel öffnet die Datei mit korrekten
  Umlauten (BOM).

## ADDED Requirements

### Requirement: Backup-Export (ZIP)

- **Ablauf:** `GET /api/recordings/{rid}/backup` — Zugriff `full`,
  `status=="done"` (sonst 409). Antwort: `application/zip` mit
  `Content-Disposition: attachment; filename="<stem>-backup-<uuid>.zip"`.
- **ZIP-Inhalt:**
  - `transcript.json` — Backup-Schema v1: `schema_version: 1`,
    `type: "polyschnack-backup"`, `exported_at`, `app_version`, Metadaten
    (Titel, original_name, Sprache, Backend, Dauer, Erstellzeitpunkt,
    `segments_manual`), Einstellungen (alle Recording-Toggles: VAD,
    Diarize inkl. Methode/Tuning, Noise-Reduce, Enhance, Punctuation,
    LLM-Enhance, Streaming; PromptTemplate/DeliveryTarget als NAME,
    nicht als DB-FK), Volltext, Segmente **inkl. Word-Timings**
    (`words[]` mit start/end/word/confidence), Transkript-Versionen
    (`TranscriptVersion`-Snapshots: version_no, kind, text, segments,
    backend, language, created_at).
  - `audio.<ext>` — Kopie des Original-Audios (`stored_path`).
  - `transcript.txt` + `transcript.srt` — Lese-Ausgabe (gerendert über
    die Standard-Templates, BOM wie Download).
  - `manifest.json` — `{"schema_version":1, "files": {"transcript.json":
    "sha256:…", "audio.mp3": "sha256:…", …}}`.
- **Datenschutz (anon):** Backups enthalten **keine DB-internen IDs**
  (keine Recording-uid, keine User-IDs) — `recording.uid` ist eine frisch
  generierte Export-UUID. `retention_minutes` (verbleibende Minuten) wird
  bei anon-Recordings im JSON vermerkt, sonst null.
- **Architektur:** neues `app/export_backup.py` (`build_backup_zip`),
  Route in `app/routers/backup.py` (oder `recordings.py`).

#### Scenario: Backup herunterladen

- **Akteure:** Besitzer (oder Share `full`).
- **Eingaben:** `GET /recordings/{rid}/backup`.
- **Ausgaben:** ZIP mit 5 Dateien; `manifest.json`-Hashes matchen den
  Dateiinhalten; `transcript.json` enthält Segmente inkl. Word-Timings
  und die Versions-Snapshots; keine DB-internen IDs.

### Requirement: Backup-Import (Restore)

- **Ablauf:** `POST /api/recordings/import-backup` (Multipart-Feld
  `file`, ZIP). Ablauf: ZIP in Temp-Datei → `manifest.json` lesen →
  SHA-256 jeder gelisteten Datei verifizieren (Mismatch → 400
  „Integritätsprüfung fehlgeschlagen") → `transcript.json` parsen →
  `schema_version` prüfen (≠1 → 400 „nicht kompatible Backup-Version") →
  Audio-Extension aus `audio.*` ableiten → Audio nach
  `storage_path_for(uid, ext, anon=…)` kopieren (Change-014-Ordner)
  → `probe_duration_path` validiert → neues `Recording` mit
  `status="done"` anlegen (Titel, original_name, Sprache, Backend, Dauer,
  Einstellungen, text, Segmente+Words aus dem Backup; `owner_user_id` =
  aktueller User; `content_hash` = SHA-256 der Audio-Datei) →
  `TranscriptVersion`-Snapshots in `version_no`-Reihenfolge anlegen.
- **Keine Neu-Transkription:** alles synchron in einem Request; das
  Recording ist sofort abspielbar und diffbar.
- **Limits:** Duplikat-Erkennung über `content_hash` (409 wie Upload);
  anon-Import unterliegt den normalen anon-Limits, Retention-Countdown
  startet beim Import.
- **Architektur:** `app/export_backup.py::import_backup_zip`, Route in
  `app/routers/backup.py`.

#### Scenario: Backup importieren (Roundtrip)

- **Akteure:** Registrierter User.
- **Eingaben:** Upload des zuvor exportierten ZIP via `import-backup`.
- **Ergebnis:** Neues Recording `status="done"` mit identischen Segmenten/
  Wörtern/Titel; Versionsliste (Diff/Restore) ist wiederhergestellt; keine
  Neu-Transkription ausgelöst.

#### Scenario: Kaputtes Backup ablehnen

- **Akteure:** Registrierter User.
- **Eingaben:** ZIP mit manipuliertem `audio.mp3` (Hash-Mismatch) bzw.
  `transcript.json` mit `schema_version: 99`.
- **Ergebnis:** 400 mit klarer Meldung („Integritätsprüfung fehlgeschlagen"
  bzw. „nicht kompatible Backup-Version"); kein Recording angelegt.
