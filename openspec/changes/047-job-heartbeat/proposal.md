# Change 047: Job-weiter Heartbeat — keine falsche Stall-Warnung bei langen Audios

**Status:** proposal
**Datum:** 2026-08-20
**Typ:** Bugfix (Change 011/035-Nacharbeit)

## Problem (User-Befund)

> „der progress mechanismus zeigt immer noch: '⚠ möglicherweise hängend ·
> keine Aktivität seit 120m 5s', selbst wenn man einen transkription GANZ
> neu startet."

Die UI zeigt die Stall-Warnung, obwohl die Transkription läuft — auch nach
komplett neuem Start.

## Root Cause

Die Heartbeats (Change 011/035) decken nur **einzelne Phasen** ab:

- `_start_heartbeat(rec_id, 21, "asr")` — nur im **Sync-ASR-Zweig**
- `_start_heartbeat(rec_id, 96, "diarization")`
- `_start_heartbeat(rec_id, 95, "postprocessing")`

**Lücken ohne Heartbeat:**
1. `preparing` (10 %): Audio laden (`read_bytes` — bei 4h52m groß)
2. `vad` (12 %): Silben-Trim
3. `enhance` (16 %): ffmpeg-Filter
4. **`convert_to_wav_16k_mono`** (nach 20 %): Konvertierung einer langen
   MP3/Opus-Datei in 16k-mono-WAV — bei der 4h52m-YouTube-Aufnahme
   dauert das MINUTEN, ohne Heartbeat
5. **Streaming-ASR-Zweig** (`transcribe_streaming`): hat gar keinen
   Heartbeat-Thread (nur on_chunk-progress, der bei langen Stillen
   pausiert)

Frontend-Logik: `stalled = status === "processing" && sinceBeat > 45 s` —
nach 45 s ohne Heartbeat erscheint die Warnung, die dann bei jedem
Polling weiter zählt („seit 120m"), obwohl der Job lebt.

„Ganz neu starten" hilft nicht: Die lange Datei läuft wieder in dieselbe
heartbeat-lose Phase (Konvertierung/Streaming).

## Lösung

**Job-weiter Heartbeat** `_start_job_heartbeat(rec_id)`:

- Startet direkt nach `audio_path.read_bytes()` im `process_recording`-try
- Tickt `last_heartbeat_at` alle 5 s über den GESAMTEN Job (alle Phasen)
- `set_progress(..., note=None)` → ändert NIE `progress_note`/
  `phase_started_at` (crud-Guard: `if note is not None`), also kein
  Konflikt mit phasen-spezifischen Heartbeats
- Liest den aktuellen `progress_pct` aus der DB (kein Rücksetzen)
- Stoppt im `finally` des Jobs (done/failed) — ein alter Heartbeat darf
  nach Re-Transcribe nicht den frischen überschreiben
- Phasen-spezifische Heartbeats bleiben (setzen die Notes weiter)

## Betroffene Dateien

- `webapp/app/service.py`: `_start_job_heartbeat()` + Einbindung in
  `process_recording` (Start im try, Stopp im finally, Init vor try)

## Tests

- Unit: `_start_job_heartbeat` tickt `last_heartbeat_at` (Fake-Session),
  stoppt auf Event, setzt NIE `progress_note`
- Regression: bestehende Heartbeat-Tests grün
- Frontend unverändert (Warnung verschwindet, sobald der Heartbeat tickt)

## Checkliste

- [ ] proposal.md
- [ ] tasks.md
- [ ] `_start_job_heartbeat` implementiert
- [ ] Einbindung in process_recording (Start/Stopp/Init)
- [ ] Tests
- [ ] Commit + Push + CI
