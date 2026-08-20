# Tasks — Change 032

1. [x] Backend: `benchmark_service.py` — `per_category` beim Re-Pooling (Manifest-Mapping sample_id→category, Mittelwerte, Sortierung)
2. [x] Backend-Tests: `test_benchmark_service.py` — Submit 2 Backends → `per_category` korrekt (wer/n je Kategorie×Backend) → 44 passed (alle Benchmark-Suiten)
3. [x] Frontend: `benchmark.ts` — `BenchmarkResults.per_category` Interface
4. [x] Frontend-Tests: `BenchmarkPage.test.tsx` — Kategorie-Charts rendern, Modell-Filter wirkt, leere Kategorie unsichtbar → 17 passed
5. [x] Frontend: `BenchmarkPage.tsx` — `CategoryQualityChart`, `ModelFilter` (Chips), leere-Kategorien-Filter, Filter-Anbindung ResultsTable+PriceComparison
6. [x] `npm test` (182 passed gesamt) + Backend-Tests grün
7. [x] Nachrüstung: `latest_results()` rüstet `per_category` bei alten latest.json on-the-fly nach (Charts funktionieren direkt nach Deploy) + Router `/results` nutzt sie + Test
8. [x] Commit + Push auf main (direkt, kein MR) + CI prüfen
