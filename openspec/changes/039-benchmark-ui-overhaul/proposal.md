# Change 039: Benchmark-UI-Überarbeitung (Matrix ohne Scrollbar, Kategorie-Filter, Mini-Tabellen)

## Problem

Die Benchmark-Sektion der Webapp-GUI hat UX-Probleme:

1. Die **Matrix** (Backends × Kategorien) passt nicht in das Feld und bekommt
   Scrollbars — sie soll immer ohne Scrollbar angezeigt werden (skalieren).
2. Beim **Kategorie-Filter** (User filtert Benchmark-Samples nach Kategorien)
   werden auch Kategorien mit 0 Samples angezeigt — nur Kategorien mit
   mehr als 0 Samples sind relevant.
3. Die **besten Modelle pro Kategorie** sollen als Teil der Kategorie
   angezeigt werden — als sehr kleine Tabelle.
4. Pro **individuellem Sample** soll eine Mini-Tabelle die Qualität
   (WER) je Modell für genau dieses Sample zeigen.

## Lösung

- Matrix: Layout so anpassen, dass sie ohne Scrollbars ins Feld passt
  (Spalten/Zeilen skalieren, kleinere Typografie, overflow sichtbar/auto
  je nach verfügbarem Platz).
- Kategorie-Filter: Kategorien ohne Samples ausblenden (Filterung nach
  backend/filter wirkt auf die Sample-Liste → Zähler = 0 → ausblenden).
- Kategorie-Block: eingeklappte/kompakte Mini-Tabelle „bestes Modell je
  Kategorie" (WER, sehr kleine Schrift, nur Top-N oder alle).
- Sample-Liste: je Sample eine Mini-Tabelle „Qualität pro Modell" (WER
  je Backend für dieses Sample, sehr klein).

## Tasks

- [x] Benchmark-Frontend lokalisieren (Template/JS/API-Datenfluss)
- [x] Matrix ohne Scrollbar rendern (table-fixed, skalierend, truncatete Header)
- [x] Kategorie-Filter: nur Kategorien mit > 0 Samples anzeigen
- [x] Mini-Tabelle „beste Modelle je Kategorie" im Kategorie-Block (sehr klein)
- [x] Mini-Tabelle „Qualität pro Modell" je Sample (per_sample aus latest.json)
- [x] Backend: per_sample in latest_results() + Re-Pooling (on-the-fly-Nachrüstung)
- [x] GUI-Test (17 Frontend-Tests + 27 Backend-Tests grün, dist gebaut)
