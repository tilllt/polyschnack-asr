# Change 162 — Queue-Phase: Diarization-Noten mit Prozentwert erkennen

**Status:** Proposed

## User-Befund (2026-08-30)

„Wenn die Diarisierung läuft, zeigt die Queue oben weiterhin 'transcription'
als Task." Die RecordingCard-Phasen-Chips zeigen korrekt „Diarisierung" —
nur die Queue-Anzeige (QueueWatcher) bleibt auf „Transcription".

## Root Cause

`_report_diar_progress` (service.py) schreibt seit Change 150/151 die Note
**mit Prozentwert**: `note=f"diarization {pct}%"` → DB enthält z. B.
`"diarization 42%"`, nie exakt `"diarization"`.

Der QueueWatcher (Change 156) prüft aber mit **exaktem Vergleich**:

```ts
j.status === "running" && j.progress_note === "diarization"
```

→ matcht nie (außer im kurzen Start-Fenster, wo process_recording einmalig
exakt `note="diarization"` setzt). Fallback: `t(`phase_${j.kind}`)` mit
`kind="transcribe"` → Anzeige „Transcription".

Dieselbe Falle steckt in `stale_jobs.py`: `rec.progress_note == "diarization"`
überspringt die Stale-Markierung nur bei exakter Note — bei
`"diarization 42%"` könnte der Watchdog eine laufende Diarization
fälschlich als hängend markieren (Schutz nur durch frisches updated_at).

## Fix

Präfix-Vergleich an beiden Stellen, konsistent mit `activePhaseIndex`
(RecordingCard.tsx), das bereits `startsWith("diarization ")` nutzt:

1. `frontend/src/components/QueueWatcher.tsx`:
   `(j.progress_note ?? "").startsWith("diarization")`
2. `app/stale_jobs.py`:
   `rec.progress_note and rec.progress_note.startswith("diarization")`

## Tests

- Backend: test_stale_processing.py um `"diarization 42%"`-Fall erweitern
  (laufende Diarization wird nicht als stale markiert).
- Frontend: Build + bestehende Tests; Logik-Äquivalenz zu activePhaseIndex.
