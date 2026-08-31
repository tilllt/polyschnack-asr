# Change 180 — Chip-Logik: Job-Status bestimmt die Phase, kein Blinken ohne Lauf

**Status:** Proposed

## Befund (2026-08-31, Live: „preparing blinkt mit runtime 8:30")

Die Phasen-Chips hatten drei Lücken:
1. **Chips nur bei `status=processing`** — align/diarize-Jobs (status bleibt
   done) zeigten nie eine Phase.
2. **pct-Fallback zu aggressiv:** note leer + pct=0 → preparing aktiv —
   auch wenn gerade ein align-Job gestartet wurde (Lücke zwischen POST und
   Worker-note).
3. **`phase_started_at` wird nie geräumt** → beim nächsten Start zeigte die
   UI die Zeit des letzten Laufs („runtime 8:30") auf der falschen Phase.

## Lösung

- **Backend:** `_schedule_realign`/`_schedule_rediarize` setzen beim Enqueue
  SOFORT note + pct=0 + phase_started_at=now (keine Restzustands-Lücke).
- **Frontend `activePhaseIndex`:** Job-STATUS-Felder (alignment/diar_status
  running|pending) haben Vorrang vor dem pct-Fallback; pct-Fallback nur
  noch bei `status=processing`; ohne aktiven Lauf → `-1`.
- **Chips-Render:** auch bei alignment/diar_status sichtbar; bei `active<0`
  alle Chips gedimmt (kein Blinken, keine Zeit).

## Betroffene Dateien

- `webapp/app/service.py`
- `webapp/frontend/src/components/RecordingCard.tsx`
- `webapp/frontend/src/progress-heartbeat.test.ts`
