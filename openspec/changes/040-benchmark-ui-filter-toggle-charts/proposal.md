# Change 040: Benchmark-UI — Filter-Toggle „Alle" + grafische Qualitätsdarstellung

## Problem

1. **„Alle"-Filter nicht umschaltbar**: Der Modell-Filter-Chip „Alle" lässt sich
   nur aktivieren, nicht wieder deaktivieren. De-Klick auf „Alle" markiert
   keines der Modelle (kein sinnvoller Zustand), erneuter Klick aktiviert alle.
   Erwartetes Verhalten: „Alle" ist ein Toggle — ist alles markiert, blendet
   ein Klick auf „Alle" alle Modelle aus (nichts markiert); sind nicht alle
   markiert, aktiviert „Alle" alles.

2. **Reine Text-Darstellung der Statistiken**: Die Modellqualität je Kategorie
   und je Sample wird als Mini-Tabelle (9px-Schrift) dargestellt. Gewünscht ist
   eine platzsparende **grafische** Repräsentation (Balken), und es muss auf
   den ersten Blick erkennbar sein, ob sich eine Grafik auf eine **Kategorie**
   oder auf ein **individuelles Sample** bezieht.

## Lösung

- **Filter-Toggle**: „Alle"-Chip bekommt echtes Toggle-Verhalten.
  - `hiddenModels.size === 0` (alle sichtbar) → Klick blendet alle Modelle aus.
  - sonst → Klick zeigt alle Modelle wieder an.
  - „Alle" reflektiert den Zustand „alle sichtbar" vs. „keins sichtbar" im
    aktiven/inaktiven Styling.
- **Grafische Darstellung (CSS-Balken, keine Chart-Lib)**:
  - `CategoryQualityChart`: horizontale Balken (Breite = relative Qualität,
    bestes Modell = volle Breite), WER als Zahl daneben, kleine Schrift,
    Header mit Kategorie-Icon/-Label (z. B. „▣ Kategorie: …") → klar als
    Kategorie-Grafik erkennbar.
  - `SampleRow`: horizontale Mini-Balken je Modell für genau dieses Sample,
    mit eindeutig anderem Icon/Label (z. B. „▤ Sample") und anderer
    Akzentfarbe → klar als Sample-Grafik erkennbar.
  - Balken via `width %` + `background` (kein Chart-Paket nötig), sehr klein
    (9–10px Schrift, 4–6px Balkenhöhe).

## Tasks

- [ ] „Alle"-Chip als Toggle (deaktivieren wenn alles sichtbar, aktivieren wenn nicht)
- [ ] CategoryQualityChart: Balken statt Tabelle, Kategorie-Label/Icons
- [ ] SampleRow: Balken statt Tabelle, Sample-Label/Icons, andere Akzentfarbe
- [ ] Tests anpassen (data-testids bleiben, Erwartungen auf Balken-Äquivalente)
- [ ] Build (dist) + Backend-Tests grün
