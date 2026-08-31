# Change 167 — Tasks

- [x] Befund: echter 297-Fall (DB-Zeiten) → Zeit-Signatur verfehlt (Lücke
      4,2 s), gestreckte Kopie (6,0 s / 3,27 s) als Signal identifiziert.
- [x] `dedupe_repeated_word_runs` um Dauer-Signatur erweitert
      (`duration_anomaly_s=2.5`, symmetrische Entfernung).
- [x] Tests: echter 297-Fall (DB-Zeiten), gestreckte zweite Kopie,
      Regression bestehender Fälle.
- [ ] Lokale Tests grün (test_chunk_overlap_dedup + Suite).
- [ ] openspec/change 167 committen, push main, CI grün.
- [ ] Box-Deploy; Live-Check Recording 297 (Re-Transcribe → Phrase 1×).
