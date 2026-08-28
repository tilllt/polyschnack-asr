# Change 151 — Progress-Bar: eigene 0..100-Balken pro Phase

**Status:** Proposed (Umsetzung läuft)

## Problem (User-Befund 2026-08-28)

Die Breiten der Progress-Bereiche bilden die erwartete Zeit NICHT ab:
Die ASR (läuft sekundenschnell) belegt 20–80 % des Balkens, die
Diarization (bei langen Filmen Minuten) steckt bei fix 96 %. Option A
(Breiten ≈ Zeit) verworfen — Option B gewählt: **jeder Schritt hat
seinen eigenen 100%-Balken, die Chips zeigen die Position in der
Abfolge** (Change 035-Chips existieren bereits).

## Lösung

Backend: alle `set_progress`-Aufrufe auf phasen-lokale pcts (0..100):

| Phase | vorher | jetzt |
|---|---|---|
| preparing/vad/enhance/separate | 10/12/16/18 | 100 (diskrete Schritte, kein Teilfortschritt) |
| asr | 20, Chunks 10–80 | 0, Chunks (i+1)/total×100 |
| alignment | 96, Gruppen 96–99.99 | 0, Gruppen (gi+1)/len×100 |
| diarization | 96 (fix) | 0, echter /progress-Wert (Change 150) |
| finalizing | 95 | 100 |

Frontend: keine Änderung nötig — der Balken rendert `progress_pct`
(jetzt phasen-lokal), die Chips (PHASES/activePhaseIndex) zeigen die
Abfolge bereits; `phaseDetail` (Chunk X/Y, X%, Gruppe X/Y) bleibt.

## Verifikation

- Backend-Suite (aligner/heartbeat/diarize) grün
- Frontend: tsc + 379 vitest grün
- Nach Deploy: Diarization-Balken füllt sich über die echten Minuten
  (0→100), ASR-Balken ist schnell voll, Chips zeigen die Position
