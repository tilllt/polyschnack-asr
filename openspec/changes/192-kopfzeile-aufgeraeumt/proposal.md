# Change 192 — Kopfzeile aufgeräumt: eine Zeile, kurz, mit Flaggen-Dropdown

## Warum

Nach Change 191 hat die Kopfzeile zwei Zeilen mit sieben Zählern, das
Nutzerbereich-Element sitzt verstreut (Name, Credits, zwei Knöpfe, Select), und
der Sprachwähler steht als nacktes `<select>` ganz rechts außen — weit weg von
allem, was mit Navigation zu tun hat. Die Zeile trägt viel Information, aber
keine Ordnung.

## Was sich ändert

- **Eine Zeile:** Logo + Menü + Sprachwahl (Flaggen-Dropdown) links, und
  **rechtsbündig** Guthaben · Username · Abmelde-/Anmelde-Symbol.
- **Sprachwähler als Flaggen-Dropdown** direkt neben dem Menü: die aktuelle
  Sprache als Flagge, Klick öffnet die Liste (🇩🇪 Deutsch · 🇬🇧 English ·
  🇧🇷 Português). Schließt per Klick außerhalb und Escape (bestehende
  `useDismiss`-Logik).
- **Status gekürzt auf drei Kennzahlen:** Anzahl der Aufnahmen, Gesamtlänge,
  Speicherbedarf. `done`, `uploaded`, `processing` entfallen (sie stehen im
  Queue-/Listenkontext, wo sie hingehören).

## Nicht Teil dieses Changes

Keine Änderung an Menüpunkten, Ansichten oder Daten. Das GPU/CPU-Badge bleibt
(es ist kein Zähler, sondern ein Betriebszustand).
