# Tasks — Change 044: Benchmark-Balken-Skalierung

## Task 1: Fix Sample-Balken (Zeile ~145)

- [ ] `pct`-Formel: `(bestW / (wer || 0.0001)) * 100`, geklemmt auf [4, 100]
- [ ] Kommentar aktualisieren (bestes Modell = volle Breite)

## Task 2: Fix Kategorie-Balken (Zeile ~348)

- [ ] `pct`-Formel: `(best / (r.wer || 0.0001)) * 100`, geklemmt auf [4, 100]

## Task 3: Tests

- [ ] Kategorie-Test prüft Breiten: 0,1 → `width: 100%`, 0,3 → `width: 33%`
- [ ] Neuer Sample-Balken-Breiten-Test (perSample 0,1 / 0,2 → 100 % / 50 %)
- [ ] Frontend-Tests grün (npm test)

## Task 4: Commit + Push

- [ ] Commit mit Change-044-Referenz
- [ ] CI grün (nach Push prüfen und melden)
