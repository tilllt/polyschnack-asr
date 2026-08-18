# Change 018 — Original-Audio im Export erhalten

## Problem

Bei Uploads in nicht-nativen Formaten (z. B. `.aac`, `.ogg`, `.opus`, `.webm`,
`.wma`) konvertiert `prepare_storage` die Datei beim Upload nach
MP3 128 kbit/s mono und **verwirft die Original-Bytes** — gespeichert wird nur
die MP3. Dadurch enthält der ZIP-Export (Backup-Download UND Account-Export
„alle eigenen Daten") die konvertierte MP3 statt des Originals. Für den User
ist die Originaldatei (z. B. ein AAC-Diktat) dann unwiederbringlich verloren —
ein Datenverlust, der sich beim Import als Qualitätsverlust bemerkbar macht.

Native Formate (`.wav`, `.mp3`, `.m4a`, `.mp4`, `.flac`) sind nicht betroffen:
sie liegen unkonvertiert im Store, der Export enthält dort bereits das Original.

## Lösung

- **Aufbewahren:** Wird beim Upload/URL-Import konvertiert, wird das Original
  zusätzlich neben der konvertierten Datei gespeichert
  (`<uuid>.orig.<ext>` im selben User-Ordner). Kein Verwerfen mehr.
- **Export:** Backup-ZIP und Account-ZIP enthalten zusätzlich
  `audio.original.<ext>` (das echte Original); die konvertierte Datei bleibt
  als `audio.<ext>` erhalten (Abspielbarkeit). Manifest deckt beide ab.
- **Import:** `import_backup_zip` bevorzugt `audio.original.*` (Original),
  fällt auf `audio.<ext>` zurück (alte Backups, rückwärtskompatibel).
  Transcodierung beim Import ist erlaubt (ffmpeg dekodiert AAC/OGG/…).
- **Bestand:** Bereits konvertierte Alt-Aufnahmen haben kein Original mehr —
  das Feature greift ab dem Deploy für NEUE Uploads.

## Betroffene Dateien

- `app/audio_utils.py` (Konvention `*.orig.<ext>`)
- `app/routers/recordings.py` (Upload: Original schreiben)
- `app/routers/url_import.py` (URL-Import: Original schreiben)
- `app/export_backup.py` (Backup-Export/Import)
- `app/routers/account.py` (Account-ZIP)
- `app/tests/test_backup_export.py` (+ neuer Test)
