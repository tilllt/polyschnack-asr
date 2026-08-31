# Change 169 — Download-Dropdown: Original-Aufnahme herunterladen

**Status:** Proposed

## User-Anforderung (2026-08-31)

„Füge in den Download-Dropdown von PolySchnack auch die Funktion hinzu,
die Original-Aufnahme herunterzuladen."

## Ist-Zustand

- Das Download-Dropdown (RecordingCard) enthält nur Transkriptions-Exporte
  (txt/srt/vtt, dynamisch aus /export-templates) und — für full/owner —
  den Backup-ZIP.
- Der Endpoint `GET /api/recordings/{rid}/audio` existiert bereits
  (Range-Streaming für den Player) und liefert die ORIGINAL-Datei
  (`stored_path`) mit `filename=rec.original_name`
  (Content-Disposition attachment) + 410 bei fehlender Datei.

## Lösung

1. **Frontend (RecordingCard):** Neuer Dropdown-Eintrag „Original-Aufnahme"
   nach den Export-Formaten (für alle mit read-Zugriff, nicht nur
   full/owner — der Player streamt die Datei ebenfalls schon für read):
   `<a href={r.audio_url} download>` — `get_audio` setzt den
   Original-Dateinamen; das `download`-Attribut erzwingt den Download.
2. **i18n:** Key `download_original` (de/en/pt) neben `backup_zip`.

Keine Backend-Änderung nötig — `get_audio` liefert Original + korrekten
Dateinamen + ehrlichen 410 bei fehlendem File (Self-Healing-Pfad der GUI).

## Tests

- Frontend-Build (tsc/vite) grün.
- Frontend-Tests: Dropdown rendert den neuen Eintrag mit
  `href === r.audio_url` und `download`-Attribut (falls
  RecordingCard-Test-Harness vorhanden; sonst Build + manueller Test).
- Manuell (Box): Download liefert die Original-Datei mit original_name.
