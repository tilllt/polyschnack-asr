# Change 023 — Self-Healing: fehlende Dateien nie mehr als Crash

## Problem

Fehlende oder verwaiste Audiodateien führten zu unvorhergesehenen
Ereignissen: Transkriptions-/Duplikat-Aufrufe auf Aufnahmen ohne Datei
(Crash zwischen File-Write und DB-Commit, manueller DB-Eingriff,
Platten-Verlust) warfen 500er bzw. unklare 409er; verwaiste Dateien im
Audio-Ordner (auf die keine DB-Zeile zeigt) fraßen Platte; der
Account-Export crashte, wenn die Audiodatei fehlte. User-Auftrag
(2026-08-15): „Wenn essentielle Dateien oder Datenbankeinträge fehlen,
darf es nie zu unvorhergesehenen Ereignissen kommen."

## Lösung (Verhaltens-Delta)

- **`audio_missing`-Flag:** Jede Recording-API-Antwort trägt
  `audio_missing: bool` (stored_path gesetzt, aber Datei nicht auf der
  Platte) — die GUI kann Aufnahmen ohne Datei sichtbar markieren
  (kein stiller Fehler).
- **410-Guards:** `transcribe_ep` und `duplicate_recording` prüfen die
  Datei vorab und antworten mit **410 „audio file missing"** statt
  500/409 — der Client kann die Aufnahme als defekt erkennen. Delete
  funktioniert weiterhin trotz fehlender Datei (räumt auf).
- **Orphan-Sweep:** `orphan_sweep.py` findet Dateien im AUDIO_DIR, auf
  die kein `stored_path` zeigt, und löscht nur Exemplare älter als
  `min_age_s` (laufende Uploads nie erfasst). Neuer Admin-Trigger
  `POST /api/admin/self-heal?dry_run=true` (Default dry_run — meldet
  nur; `dry_run=false` löscht).
- **Account-Export:** `GET /api/account/export` (eingeloggt) liefert
  ein ZIP aller EIGENEN Recordings (1 Ordner je Aufnahme: Audio +
  `transkription.json`); fehlt die Datei, wird `AUDIO_FEHLT.txt` in den
  Ordner gelegt statt zu crashen. Keine Shares/Fremde.

## Betroffene Verhaltensbereiche

- **Transcription (MODIFIED):** `audio_missing`-Flag + 410-Guards —
  siehe `specs/transcription/spec.md`.

## Downgrade

- `audio_missing`-Feld aus `_recording_to_dict` entfernen; Guards durch
  altes Verhalten ersetzen; self-heal-Endpunkt entfernen. Keine
  Datenmigration nötig.
