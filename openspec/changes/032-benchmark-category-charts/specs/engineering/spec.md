# Spec — Change 032: Benchmark-Kategorie-Graphen

## REQ-BEN-046 — `per_category` in `latest.json`

- `POST /api/benchmark/submit` (bzw. `BenchmarkService.submit_results`) schreibt
  zusätzlich `per_category` in `results/latest.json`.
- Format: Array von Objekten `{category: string, backend: string, wer: number,
  cer: number, n: number}` — ein Eintrag je (Kategorie, Backend) mit Daten.
- Berechnung beim Re-Pooling: über alle Run-Dateien mit aktuellem
  `manifest_sha256`; je Row die Kategorie über das aktive Manifest mappen
  (`sample_id` → `category`); Rows ohne `sample_id` oder ohne
  `wer`-Wert entfallen. `wer`/`cer` = Mittelwert über die Samples der
  (Kategorie, Backend)-Zelle, `n` = Anzahl.
- Sortierung: nach `category`, dann `backend` (deterministisch).
- `rows` (gepoolte Gesamtwerte) bleibt unverändert — additiv, keine
  Breaking-Änderung für bestehende Clients.
- `GET /api/benchmark/results` liefert das Feld unverändert durch.

## REQ-BEN-047 — Kategorie-Qualitäts-Graphen (Frontend)

- Neuer Abschnitt „Modellqualität je Kategorie" auf der Benchmark-Seite,
  nach der 2-Achsen-Matrix, vor „Samples".
- Für jede Kategorie mit mindestens einem Datenpunkt (`per_category`):
  ein Balken-Graph. Je Modell ein horizontaler Balken:
  - Balkenbreite = WER (%), Wert-Label rechts am Balken („8,3 %"),
    Modellname links.
  - Sortierung je Kategorie nach WER aufsteigend (bestes Modell oben).
  - Feste Farbe je Modell (Palette, konsistent über alle Kategorien).
  - Bei >0 Samples im Manifest: Titel „Kategorie (n Samples)".
- Abgewählte Modelle (Modell-Filter) erscheinen in keinem Graphen; ist in
  einer Kategorie kein Modell mehr aktiv, entfällt der Graph.

## REQ-BEN-048 — Modell-Filter (Frontend)

- Oben auf der Seite (Header-Zeile) Chips für jedes Backend aus
  `results.per_category` (+ `results.rows` als Fallback): Klick toggelt das
  Modell; Auswahl als `Set<string>`; leere Auswahl = alle Modelle aktiv.
- Der Filter wirkt auf: Kategorie-Graphen, `ResultsTable`, `PriceComparison`.
- UI-Regel: abgewählte Modelle nie still Altdaten zeigen — die betroffenen
  Ansichten filtern konsistent; „Alle anzeigen"-Reset-Chip.

## REQ-BEN-049 — Leere Kategorien ausblenden (Frontend)

- In der Samples-Sektion werden Kategorien mit `samples.length === 0` nicht
  mehr gerendert (auch nicht als leere Box mit „(0)").
