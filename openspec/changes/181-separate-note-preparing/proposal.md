# Change 181 — "separate"-Note (Musik-Entfernung) → Phase preparing

**Status:** Proposed

## Befund (2026-08-31, Matrix-Audit aller progress_note-Setter)

`activePhaseIndex` kannte alle Backend-Noten außer `"separate"`
(service.py:2384 — Musik-Entfernungs-Phase im re-transcribe mit Methode
A/B). Ohne Mapping fiel die Phase auf den pct-Fallback: pct=100 →
„finalizing" — die Chips zeigten während der Separation fälschlich die
letzte Phase.

## Lösung

`"separate"` → Phase 0 (preparing) in `activePhaseIndex` + Testfall.

## Verifikation (vollständige Noten-Matrix, aus dem Code extrahiert)

preparing/vad/enhance/separate → 0 · asr → 1 · diarization → 2 ·
alignment → 3 · finalizing/postprocessing → 4. Alle Modi abgedeckt:
transcribe/re-transcribe (preparing→vad→enhance→separate→asr→
diarization→finalizing), realign (alignment), re-diarize (diarization).

## Betroffene Dateien

- `webapp/frontend/src/components/RecordingCard.tsx`
- `webapp/frontend/src/progress-heartbeat.test.ts`
