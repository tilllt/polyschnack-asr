# Change 051: Benchmark-Grafiken zeigen ASR-Qualität statt WER-Fehlerrate

**Status:** proposal
**Datum:** 2026-08-20
**Typ:** UI-Bugfix (Benchmark-Seite)

## Problem

User-Befund 2026-08-20 (Screenshot): Auf der Benchmark-Seite stehen unter
„Sample-Qualität" alle Balken auf **0.0%** — obwohl die Daten korrekt sind
(WER je Sample je Modell, 207 Samples, verifiziert im /results-Endpoint).

Zwei Fehler:

1. **Falscher Begriff**: „Sample-Qualität" suggeriert die Qualität der
   Audiosamples. Gemeint ist die **Qualität der Spracherkennung** (WER
   der Modelle) für dieses Sample.
2. **Fehlerrate statt Qualität**: Angezeigt wird `wer * 100` % — die
   FEHLERRATE. WER 0.0 (= perfekte Erkennung, z. B. einfacher Satz, den
   alle Modelle fehlerfrei transkribieren) erscheint als „0.0%" und sieht
   wie „keine Qualität" aus. Bei einfachen Samples steht dann bei allen
   Modellen 0.0% — exakt der Screenshot-Befund.

## Lösung

Qualität = `(1 - wer) * 100` % — **100 % = fehlerfrei**, intuitiv:

- **Sample-Grafik**: Beschriftung „Sample-Qualität" → **„ASR-Qualität"**
  (klar: Erkennungsqualität der Modelle für dieses Sample). Balkenbreite
  und Zahlenwert = `(1-wer)*100` (absolut, geclamped auf [0, 100];
  Mindestbreite 4 px für Sichtbarkeit). Tooltip zeigt weiterhin den
  rohen WER („WER 12,5 %") für Fachleute.
- **Kategorie-Grafik**: gleiche Umstellung (Wert + Balkenbreite =
  `(1-wer)*100`), Tooltip „WER x % (n Samples)" bleibt.

Balkenbreite wird dadurch absolut interpretierbar (100 % = perfekt)
statt relativ zum besten Modell (Change 040/044-Design, bei dem das
beste Modell immer 100 % hatte — unabhängig von seiner tatsächlichen
Qualität).

## Abgrenzung

- Kein Backend-Change: /results liefert per_sample/per_category korrekt.
- RTF bleibt unverändert (Tooltip/preislich, nicht Teil dieser Grafik).
