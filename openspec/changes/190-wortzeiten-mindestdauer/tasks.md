# Tasks — Change 190

- [x] `word_anchors.enforce_min_word_durations(words, floor=0.08, seg_end=None)`
- [x] Tests: Null-Dauer wird auf 80 ms gehoben; Wort mit Folgewort am gleichen
      Start wird korrigiert; Reihenfolge bleibt monoton; kein Überschreiten der
      Segmentgrenze; echte Dauern bleiben unangetastet
- [x] Verdrahtung: `service._run_align_phase` (nach `resolve_zero_durations`)
      und `routers/segments.reconcile_words_to_text`
- [x] Regressionstest aus Aufnahme 328: „ist" in Segment 6 hat danach ≥ 80 ms
- [x] Messung komprimierter Abschnitt (Direktaufruf Aligner) → Befund in
      `design.md`: Aligner plausibel, Ursache im eigenen Fenster/Offset
- [ ] Verifikation in Prod an 328: Re-Align, danach 0 Wörter < 80 ms und
      Segment 6 plausibel (>= 0,2 s/Wort oder Ursache dokumentiert)
- [ ] Folge-Change: Gruppenfenster/Offset im Align-Pfad instrumentiert prüfen
