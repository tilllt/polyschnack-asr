# Change 128 — Cancel-Button für Rediarize/Background-Align sichtbar machen

## Problem

User-Befund (2026-08-25): „Man kann diarize und align immer noch
nicht abbrechen — wo ist der Button?" Auf dem Handy ist bei laufender
Rediarize nur der bg-diar-Hinweis sichtbar („Diarization running in
background … · running for XXs") — **ohne Cancel**.

Code-Befund: Der Cancel-Button (`RecordingCard.tsx` ~Z. 1925) liegt
im Desktop-Bereich neben dem Versions-Dropdown und deckt
`status processing/queued` sowie `done + alignment running/pending`
ab — aber **nicht** `done + diar_status running/pending`. Zudem ist
er auf Mobile nicht auffindbar (der User sieht nur den bg-Hinweis).

## Analyse (Ist-Zustand, code-verifiziert)

- Backend-Cancel (Change 124) funktioniert für Diar+Align; die
  Response liefert `diar_status` bereits (`recordings.py` Z. 607).
- Die sichtbaren Live-Hinweise bei Hintergrund-Jobs sind
  `bg-align` (Z. ~1338) und `bg-diar` (Z. ~1386) — beide ohne Button.

## Lösung

1. Cancel-Button in den **bg-diar-Hinweis** (mobile-sichtbar):
   `handleCancelJob` + `cancelMut`-Status, kompakter Link-Stil.
2. Cancel-Button in den **bg-align-Hinweis** (gleiches Muster).
3. Die zuvor erweiterte Bedingung am Desktop-Button bleibt auf den
   Original-Stand zurückgesetzt (Rediarize-Cancel läuft jetzt über
   den Hinweis-Button — eine eindeutige, überall sichtbare Stelle).

## Betroffene Dateien

- `webapp/frontend/src/components/RecordingCard.tsx`
- `webapp/frontend/src/components/RecordingCard.test.tsx`

## Verifikation

1. Frontend-Tests: Cancel-Button im bg-diar- und im bg-align-Hinweis;
   kein Button bei done ohne laufende Hintergrund-Jobs.
2. Frontend-Gesamtsuite + Build grün.
