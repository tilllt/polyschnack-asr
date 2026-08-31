# Change 170 — Design

## Problem

`activePhaseIndex` ist auf `progress_note` (Phasen-Keys) + pct-Fallback
angewiesen. Die Hintergrund-Jobs (align/rediarize) schrieben weder Note
noch `phase_started_at` → die Anzeige zeigte den Zustand des zuletzt
abgeschlossenen Transcribe-Laufs: pct=100 → „finalizing" blinkt,
`processing_started_at`/`phase_started_at` stundenalt → „läuft seit 180m".

## Lösung

`crud.set_progress` ist der etablierte Pfad (pct + heartbeat +
`phase_started_at` bei Notenwechsel) — die Worker nutzen ihn jetzt für den
Job-Start mit dem passenden Phasen-Key. Kein neuer Mechanismus, kein
Frontend-Fix nötig (`activePhaseIndex` erkennt `alignment`/`diarization`
bereits).

## Design-Entscheidungen

- pct = 1 beim Start: ehrlich („läuft, Fortschritt unbekannt"), statt die
  alte 100 %-Anzeige stehen zu lassen („fertig?").
- `phase_started_at` = Job-Start: die Align-/Diar-ETA (recordings.py nutzt
  `elapsed_since(rec.phase_started_at)`) rechnet ab jetzt korrekt ab
  Job-Beginn statt ab dem alten Transcribe.
- Note wird am Job-Ende wie bisher geräumt (`progress_note = None`).

## Offene Fragen

Keine. Verifikation: Live-Test auf der Box (Chip „aligning" während
„New word timestamps"-Lauf).
