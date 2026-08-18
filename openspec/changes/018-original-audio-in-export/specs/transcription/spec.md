## ADDED Requirements

### Requirement: Original-Audio wird bei Konvertierung aufbewahrt

- **Ablauf:** `prepare_storage` liefert weiterhin die Store-Daten; der
  Upload-Flow (`upload_recording`) und der URL-Import legen bei einer
  Konvertierung (`conv_note` gesetzt) zusätzlich die unveränderten
  Original-Bytes ab als `audio_utils.original_path(stored)` =
  `<stored>.orig<Original-Suffix>` (gleicher User-Ordner). Native Formate
  (`.wav/.mp3/.m4a/.m4b/.mp4/.flac`) und der verlustfreie M4A-Faststart-Remux
  speichern kein Duplikat — dort ist der Store-Inhalt bereits das Original.
- **Warum:** Bisher wurden die Original-Bytes nach der Konvertierung
  verworfen; der Export konnte nur die konvertierte MP3 liefern, das
  Original war unwiederbringlich verloren.
- **Architektur:** `app/audio_utils.py` (Konvention), `app/routers/recordings.py`
  (Upload), `app/routers/url_import.py` (URL-Import).

#### Scenario: AAC-Upload mit Konvertierung

- **Akteure:** User lädt `diktat.aac` hoch.
- **Eingaben:** `prepare_storage` konvertiert nach MP3 (conv_note gesetzt).
- **Ergebnis:** Im Store liegen beide Dateien: `<uuid>.mp3` (abspielbar) und
  `<uuid>.mp3.orig.aac` (Original, unverändert).

#### Scenario: Nativer Upload

- **Eingaben:** User lädt `aufnahme.m4a` hoch (nativ, ggf. Faststart-Remux).
- **Ergebnis:** Nur die Store-Datei — kein Duplikat, da Inhalt == Original.

### Requirement: ZIP-Exporte enthalten die Original-Datei

- **Ablauf:** `build_backup_zip` und `_zip_recordings` (Account-Export) legen
  zusätzlich zur Store-Datei (`audio.<ext>`) die Original-Datei als
  `audio.original.<ext>` hinein, wenn sie existiert. Das Manifest
  (`manifest.json`) hash-t beide Dateien. Fehlt die Original-Datei
  (Alt-Bestand), bleibt der Export wie bisher (nur `audio.<ext>`).
- **Warum:** Der User erwartet im Export die Originaldatei; die konvertierte
  Version bleibt für Abspielbarkeit und Rückwärtskompatibilität erhalten.
- **Architektur:** `app/export_backup.py` (`build_backup_zip`),
  `app/routers/account.py` (`_zip_recordings`).

#### Scenario: Backup einer konvertierten Aufnahme

- **Eingaben:** Aufnahme mit Original-Seitendatei; GET `/api/recordings/{rid}/backup`.
- **Ergebnis:** ZIP enthält `audio.mp3` UND `audio.original.aac`, Manifest
  deckt beide ab.

### Requirement: Import bevorzugt die Original-Datei

- **Ablauf:** `import_backup_zip` sucht zuerst `audio.original.*`; existiert
  sie, wird sie als Audio-Quelle genutzt (Extension/MIME aus ihrem Suffix,
  Dauer via ffprobe). Sonst `audio.<ext>` (alte Backups). Erlaubte
  Transcodierung: ASR-Backends und Player dekodieren das Original via ffmpeg.
- **Warum:** Der Roundtrip soll das Original wiederherstellen, nicht die
  konvertierte Version.
- **Architektur:** `app/export_backup.py` (`import_backup_zip`).

#### Scenario: Import mit Original

- **Eingaben:** Backup-ZIP mit `audio.original.aac` + `audio.mp3`.
- **Ergebnis:** Neues Recording speichert die `.aac`-Datei (nicht die MP3);
  `stored_path` zeigt auf die Original-Datei.

#### Scenario: Altes Backup ohne Original

- **Eingaben:** Backup-ZIP nur mit `audio.mp3` (vor diesem Change).
- **Ergebnis:** Import nutzt `audio.mp3` — unverändert wie bisher.
