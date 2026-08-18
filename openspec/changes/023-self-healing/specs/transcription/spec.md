## ADDED Requirements

### Requirement: Selbstheilung bei fehlender Audiodatei

- **Ablauf:** Jede Recording-API-Antwort trägt `audio_missing: bool`
  (True, wenn `stored_path` gesetzt ist, die Datei aber nicht auf der
  Platte liegt). `transcribe_ep` und `duplicate_recording` prüfen die
  Datei vorab und antworten mit **410 „audio file missing"** statt
  500/409. `DELETE` funktioniert weiterhin trotz fehlender Datei.
  Admin kann verwaiste Audio-Dateien per
  `POST /api/admin/self-heal?dry_run=true` finden (Default dry_run —
  meldet nur; `dry_run=false` löscht Dateien älter als 1 h, auf die
  kein `stored_path` zeigt).
- **Ergebnis:** Aufnahmen ohne Datei sind sichtbar markiert
  (`audio_missing`), Jobs auf ihnen scheitern sauber mit 410 statt
  Crash; verwaiste Dateien werden kontrolliert entfernt.
- **Architektur:** `routers/recordings.py` (`_ensure_audio_present`,
  `_recording_to_dict`), `orphan_sweep.py`, `routers/admin.py`
  (self-heal), `routers/account.py` (Export mit `AUDIO_FEHLT.txt`).

#### Scenario: Transkription bei fehlender Datei

- **Akteure:** Besitzer einer Aufnahme, deren Audiodatei fehlt
  (z.B. nach Platten-Verlust).
- **Eingaben:** `POST /api/recordings/{id}/transcribe`.
- **Ergebnis:** 410 „audio file missing"; Recording bleibt mit
  `audio_missing=true` sichtbar; kein 500, kein Job in der Queue.

#### Scenario: Admin räumt verwaiste Dateien auf

- **Akteure:** Admin.
- **Eingaben:** `POST /api/admin/self-heal?dry_run=false`.
- **Ergebnis:** Alte, un-referenzierte Audio-Dateien werden gelöscht;
  frische (laufende Uploads) und referenzierte bleiben; Antwort listet
  die entfernten Dateien.
