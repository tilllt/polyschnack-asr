# Change 135: Benchmark-GUI — Tabs, Sample-Player, Hypothese-Text

## Problem

Die Benchmark-Seite zeigt ASR/VAD/Aligner-Ergebnisse untereinander in einer
langen Seite. Der User will:

1. **Tabs** für die vier Test-Suites (ASR, VAD, Align, Diar) statt einer
   Endlos-Seite.
2. In **jedem** Tab: das getestete Sample **anhören** können + einen
   **Graphen** sehen, wie das jeweilige Modell/Methode abgeschnitten hat
   (wie es bei ASR schon ist: WaveformPlayer + CSS-Balken je Modell).
3. **Collapse/Expand-Leiste unten am Rand** für die Kategorien — nach dem
   Durchhören einer Kategorie soll man unten weitermachen können, ohne
   wieder ganz nach oben zu scrollen.
4. Bei den **ASR-Benchmarks**: unter den Balken den **erkannten Text**
   (Hypothese) anzeigen, den die Modelle STATT des Ground Truth erkannt
   haben.

## Ziel

- Tab-Navigation (ASR | VAD | Align | Diar) mit persistenter Auswahl.
- ASR-Tab: Samples nach Kategorie (collapsible) + Hypothese-Text je Modell
  unter den Balken.
- VAD-Tab: VAD-Ergebnisse (F1 etc.) + VAD-Samples mit Player + je Modell
  Graph.
- Align-Tab: Aligner-Ergebnisse + Samples mit Player + Graph (Wortabdeckung).
- Diar-Tab: Platzhalter „noch keine Daten" (Diar-Benchmark-Suite folgt als
  eigener Change).
- Sticky Collapse/Expand-Leiste am unteren Rand: zeigt die Kategorien als
  Knöpfe (alle zu-/aufklappen, Sprung zur Kategorie).

## Nicht-Ziel

- Kein Diar-Benchmark-Datensatz hier (eigener Change 136).
- Keine VAD/Align-Test-Set-Änderungen (Test-Set-Qualität = eigener Change).

## Kontext

- `webapp/frontend/src/components/BenchmarkPage.tsx` (1178 Zeilen) enthält
  bereits: `BenchmarkCategory`, `SampleRow` (Player + Mini-Balken),
  `VadResultsTable`, `AlignerResultsTable`, `BenchmarkVadSamples`,
  `CategoryQualityChart`.
- `webapp/frontend/src/benchmark.ts`: Typen `BenchmarkResults`, `ResultRow`,
  `VadResultRow`, `AlignerSummaryRow`, `per_sample` (sample_id → backend →
  wer).
- Backend: `webapp/app/routers/benchmark.py` + `benchmark_service.py`.
- Hypothese-Text: `per_sample` liefert aktuell nur WER-Zahlen; der
  erkannte Text müsste aus den Benchmark-Run-Daten kommen (Runner speichert
  aktuell kein Transkript — Backend-Erweiterung in diesem Change).
