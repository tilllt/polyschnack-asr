# Change 135 — Tasks

## 1. Backend: Hypothese-Text je Sample/Modell

- [x] `benchmark_service.py`: `per_sample_text` (sample_id → {backend: text})
      on-the-fly in `latest_results()` + beim Submit in `apply_submission()`
      aus den Run-Rows (`rows[].hyp`, submitted der Runner bereits)
- [x] `/api/benchmark/results` liefert `per_sample_text`
- [x] Tests: `test_apply_submission_pools_per_category` (hyp-Assertions) +
      `test_latest_results_rueckt_per_sample_text_nach` — 16 passed

## 2. Frontend: Tabs

- [x] `BenchmarkPageContent`: Tab-Leiste (ASR | VAD | Align | Diar),
      aktiver Tab als State, localStorage-Persistenz (try/catch-gesichert)
- [x] ASR-Tab = Samples-Sektion + Methodik + Matrix + Ergebnisse + Preise
- [x] VAD-Tab = VadResultsTable + BenchmarkVadSamples
- [x] Align-Tab = AlignerResultsTable + Samples-Liste (Player, derselbe Testset)
- [x] Diar-Tab = Empty-State „noch keine Daten" (Change 136 verweist)
- [x] Tab-Auswahl bleibt beim Reload erhalten (localStorage)

## 3. Frontend: Hypothese-Text unter ASR-Balken

- [x] `SampleRow`: unter den Balken je Modell den erkannten Text anzeigen
      (aus `per_sample_text`), nur wenn vorhanden (alte Runs ohne)

## 4. Frontend: Collapse/Expand-Leiste unten

- [x] Sticky-Leiste (`fixed bottom-0`): Kategorie-Chips (Anzahl), „Alle auf/zu",
      Sprung per scrollIntoView (rAF), Aktiv-Markierung
- [x] In ASR- UND Align-Tab (VAD hat eigene Gruppen)

## 5. Frontend: SuiteExplainer (Laien + Profi je Tab)

- [x] `SuiteExplainer.tsx`: Laien-Teil („Was wird hier getestet?" + „So liest du
      die Ergebnisse") immer sichtbar; Profi-Details (Methodologie, Metriken,
      Modelle, Quellen) per Toggle einblendbar — für ASR/VAD/Align/Diar
- [x] In allen 4 Tabs eingebaut

## 6. Tests + Gate

- [x] Frontend: 7 neue Tests (Tabs, localStorage, Collapse-Leiste, Hypothese,
      ohne-Hypothese) + 7 Explainer-Tests + 2 alte Tests an Tab-Struktur
      angepasst — 356 passed, tsc clean, `npm run build` OK
- [x] Backend: per_sample_text-Tests — 16 passed (benchmark_service)

## 7. Commit, Push, CI

- [ ] Commit, Push, CI-Watch bis success
