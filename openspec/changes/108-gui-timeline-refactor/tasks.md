# Tasks — Change 108 (GUI/Workflow-Refactoring: Timeline als Source of Truth)

> Konzept-Change: Dieses Change liefert proposal.md + design.md (Analyse +
> Ziel-Architektur + Migrationspfad). Umsetzung als Folge-Changes M1–M5.

## Konzept (dieser Change)
- [x] proposal.md: Problem, Wurzel-Analyse, Ziel-Architektur (Timeline-SoT,
      Invarianten, VAD-Offset, reprocess-Pipeline, Waveform, Timeline-Store),
      Migrationspfad M1–M5, Verifikation
- [x] design.md: Befund-Katalog mit Code-Belegen (B1–B6 Backend, F1–F4 Frontend)
      + Detail-Architektur T1–T6 + offene Fragen
- [ ] Commit + Push
- [ ] Review mit User (Priorisierung M1–M5, offene Fragen)

## Folge-Changes (nach Konzept-OK)
- [ ] M1: Datenmodell (Wortliste mit source/confidence, ein Zeitformat, Backfill)
- [ ] M2: Backend-applyOps + Invarianten + llm_enhance-words-Fix (B3)
- [ ] M3: reprocess-Pipeline (align/diarize/asr-Bereich)
- [ ] M4: Frontend-Timeline-Store + Editor-Umbau + Waveform ohne Auto-Region (F2)
- [ ] M5: Playback-Sync aus einer Position

## Sofort-Fixes (unabhängig vom Refactor, niedrig hängend)
- [ ] F2: Auto-Region entfernen (WaveformPlayer Z. 523–529) — keine Auto-Markierung
- [ ] B3: llm_enhance schreibt words mit (sonst text/words-Drift)
