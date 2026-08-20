# Tasks — Change 051: Benchmark-Grafiken zeigen ASR-Qualität

## Task 1: Sample-Grafik

- [x] Beschriftung „Sample-Qualität" → „ASR-Qualität je Modell"
- [x] Balkenbreite + Zahlenwert = (1-WER)*100 (absolut, clamp [0,100],
      Mindestbreite 4 px); Tooltip zeigt Qualität + rohen WER
- [x] bestW-Relativskala (Change 040/044) entfernt

## Task 2: Kategorie-Grafik

- [x] Label „Kategorie · X — ASR-Qualität"
- [x] Balkenbreite + Zahlenwert = (1-WER)*100; Tooltip Qualität + WER + n

## Task 3: Tests

- [x] CategoryQualityChart: 90.0 %/70.0 % statt 10.0 %/30.0 %; Breiten 90/70
- [x] Sample-Balken: Breiten 90/80 (absolut)
- [x] Label-Test „ASR-Qualität je Modell" („Sample-Qualität" verschwindet)
- [x] Regression Screenshot-Befund: WER 0.0 → „100.0 %" (nie 0.0 %)
- [x] 193/193 Frontend-Tests grün, tsc sauber

## Task 4: Commit

- [ ] Commit + Push + CI
