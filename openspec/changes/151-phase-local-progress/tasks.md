# Change 151 — Tasks

## 1. Backend (phasen-lokale pcts)

- [x] preparing/vad/enhance/separate: 10/12/16/18 → 100
- [x] asr-Start 20 → 0; _on_chunk (i+1)/total×100
- [x] alignment-Start 96 → 0; Gruppen 96+…→ (gi+1)/len×100
- [x] diarization 96 → 0; _report_diar_progress pct echt (Change 150)
- [x] finalizing 95 → 100 (beide Pfade)
- [x] on_progress-Lambda auch in der Haupt-Pipeline (rediarize hatte ihn schon)

## 2. Tests

- [x] test_aligner: Assertion auf Start 0 + note (phasen-lokal)
- [x] Backend-Suite grün (33 passed)
- [x] Frontend tsc + 379 vitest grün

## 3. Abschluss

- [ ] Commit + Push + CI
- [ ] Nach Deploy: Balken-Verteilung real prüfen
