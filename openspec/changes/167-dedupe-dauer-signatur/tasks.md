# Change 167 — Tasks

- [x] Befund: echter 297-Fall (DB-Zeiten) → Zeit-Signatur verfehlt (Lücke
      4,2 s), gestreckte Kopie (6,0 s / 3,27 s) als Signal identifiziert.
- [x] `dedupe_repeated_word_runs` um Dauer-Signatur erweitert
      (`duration_anomaly_s=2.5`, symmetrische Entfernung).
- [x] Tests: echter 297-Fall (DB-Zeiten), gestreckte zweite Kopie,
      Regression bestehender Fälle — lokal 10/10 grün, CI-Suite grün.
- [x] openspec/change 167 committen (75ca3aa), push main, CI test-webapp
      + build-webapp grün.
- [x] Box-Deploy (Revision 75ca3aa5).
- [x] Live-Check: Re-Transcribe Recording 297 (Run 141, Ergebnis 131) —
      „Im anliegenden Ort" bei 8:40 jetzt GENAU EINMAL; die gestreckte
      Stille-Kopie (519,6–529,4 s) wurde entfernt, echte Kopie bleibt.
