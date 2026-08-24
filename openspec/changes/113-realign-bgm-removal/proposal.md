# Change 113 — Re-Align mit BGM-Removal (separate_backend)

## Proposal

### Problem (User-Befund, 24.08., tilllt)

„Neue PolySchnack Images live immer noch kein aligner — wenn man Re-align
drückt, kann man nicht die bgm Removal auswählen."

Beim **Re-Transcribe** kann der User seit Change 106 den Music-Remover wählen
(`separate_backend`), beim **Re-Align** nicht:

- Backend-Route `POST /recordings/{rid}/realign` (`segments.py`) akzeptiert
  **kein** `separate_backend`-Feld (kein Form-Param, keine Durchreichung).
- `_schedule_realign(rec_id)` (`service.py` Z. 1045) lädt die **Original-
  Audiodatei**, reproduziert nur VAD-Trim/Enhance aus dem Run — **kein
  Music-Removal**, nicht einmal aus den Run-Settings des zugehörigen Runs.
- Frontend `realignRecording(id)` sendet **keinen Body**; der Re-Align-Button
  hat kein Auswahl-Feld.

Konsequenz: Bei Musik-Aufnahmen (z. B. Saison-Couplets mit Begleitung) läuft
der Forced-Aligner auf dem Original-Audio inkl. Begleitung → schlechtes oder
kein Wort-Alignment (alignment=skipped, „⚠️ Alignment übersprungen"-Hinweis,
Change 101) — der Aligner „kann nichts" mit der Musik.

### Ziel

Re-Align bietet dieselbe BGM-Removal-Auswahl wie Re-Transcribe:

1. **Backend:** `realign_recording` akzeptiert `separate_backend` (Form,
   Default `"none"`, isinstance-Guard wie in den Change-106-Routen) und reicht
   es an `_schedule_realign(rec_id, separate_backend)` durch.
2. **Service:** `_schedule_realign` führt nach VAD-Trim/Enhance die Separation
   aus (SeparateClient, `htdemucs` | `mel-band-roformer`), falls gewählt —
   identische Logik/Reihenfolge wie die Transkriptions-Pipeline (service.py
   Z. 1569–1588: health → separate → vocals, ehrlicher Fallback „weiter mit
   Original" bei nicht erreichbar/leer/Fehler). Der Alignment-Cache bekommt
   die Vocals + denselben `trim_offset_s` → konsistente Zeitbasis.
3. **Frontend:** `realignRecording(id, { separate_backend })` sendet FormData;
   der Re-Align-Button bekommt ein kleines Auswahl-Feld
   (Sep: aus / htdemucs / melband — gleiche Optionen wie FeatureToggles
   Z. 156–158), Wert wird beim Klick mitgesendet.

### Nicht-Ziel

- Kein neues Backend, kein neues Modell.
- Keine Änderung an Re-Diarize (analog betroffen? separat prüfen — aktuell
  nicht Teil des User-Befunds).
- Der Aligner selbst bleibt unverändert (qwen3-forced-aligner).

### Verifikation

- Backend-Tests: realign-Route mit/ohne `separate_backend` (Form), Guard bei
  direkten Aufrufen; `_schedule_realign` mit gemocktem SeparateClient
  (vocals ersetzen Audio, Fallback bei Fehler).
- Frontend: Select rendert, FormData enthält das Feld.
- Nach Deploy: saisoncouplet → Re-Align mit „Sep: htdemucs" → alignment
  läuft auf Vocals.
