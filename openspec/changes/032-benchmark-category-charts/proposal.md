# Change 032 — Benchmark-Visualisierung: Modellqualität je Kategorie + Modell-Filter

## Problem

Die Benchmark-Seite (`/benchmark`) zeigt Ergebnisse nur als **gepoolte
Gesamttabelle** (ein WER-Wert je Backend über alle Samples). Für die
Entscheidungsfindung („welches Backend für welche Störungsart?") fehlt die
**Kategorie-Ebene**: Wie gut ist jedes Modell bei `telefon`, `tonband`,
`film` oder `akzent`? Zusätzlich blenden leere Kategorien (z. B. nach
Matrix-Zellen-Filter) als leere Boxen mit „(0)" — unnötiges Rauschen.

## Ziel

1. **Ein Qualitäts-Graph je Sample-Kategorie**: horizontale Balken, ein
   Balken pro Modell (WER %), sortiert nach WER aufsteigend (bestes oben).
   Datenquelle: gepoolte Ergebnisse auf Kategorie-Ebene.
2. **Modell-Filter oben auf der Seite**: Chips zum An-/Abwählen der Modelle;
   wirkt auf alle Kategorie-Graphen, die Ergebnis-Tabelle und den
   Preisvergleich (leere Auswahl = alle).
3. **Kategorien mit 0 Samples ausblenden** (nicht als leere Box zeigen).

## Entscheidungen

- **Backend liefert `per_category` in `latest.json`**: `[{category, backend,
  wer, cer, n}]`, beim Re-Pooling aus den Run-Rows berechnet. Die Kategorie
  wird serverseitig über das aktive Manifest gemappt (`sample_id` →
  `category`) — die Runner-Rows brauchen keine Änderung (sie senden nur
  `sample_id`).
- **Kein neues Chart-Framework**: die 26 kleinen Balken-Charts werden als
  reine CSS/HTML-Balken gerendert (kein echarts-Dependency, mobiltauglich,
  vitest-testbar). Muster aus dem ECharts-Skill (feste Modellfarbe über alle
  Charts, Label an jedem Balken, Sortierung) werden als CSS-Varianten
  übernommen.
- **Modell-Filter**: `Set<string>` in der Page; Chips im Header; leere
  Auswahl = „alle". Wirkt auf: Kategorie-Graphen, `ResultsTable`,
  `PriceComparison` (Filter-Helper zentral, ein Render-Einstieg).
- **Leere Kategorien**: in der Samples-Sektion wird eine Kategorie mit 0
  Samples nicht mehr gerendert.

## Nicht-Ziele

- Keine Runner-Änderung (Sample-Rows bleiben ohne `category`).
- Kein Chart-Klick-Verhalten (keine Links aus den Balken).
- Kein neues Endpunkt-Schema für alte Clients (`rows` bleibt unverändert,
  `per_category` ist additiv).
