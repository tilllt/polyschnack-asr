# Change 122 — Tag-Filter-Falle: Leer-Zustand behält Filterleiste

## Problem

Klick auf einen vorhandenen Tag (Filter-Chip) kann zu 0 Treffern führen
(z. B. Suchbegriff + Tag kombiniert, oder Tag-Mismatch). `RecordingList`
rendert bei **leerer Trefferliste** einen Early-Return (Leer-Zustand)
OHNE Sort-Badges und OHNE Tag-Chips:

- Alle Files verschwinden
- Die Filter-/Sortieroptionen verschwinden ebenfalls
- Der aktive Tag-Filter ist nicht mehr abwählbar — der User hängt fest

User-Report (2026-08-25): „Ich klicke auf einen vorhandenen Tag: alle
Files verschwinden, aber auch der Tag Filter und sortieroptionen. Tag
anklicken: keine Transkription wird mehr gezeigt, man kann den Filter
aber auch nicht mehr abwählen."

## Lösung

- `mergeChipTags(tagList, activeTags)` (neu, sortState.ts): ergänzt
  AKTIVE Tags, die in der Trefferliste nicht (mehr) vorkommen, als Chips
  mit count 0 → Filter bleibt sichtbar und abwählbar.
- `RecordingList` rendert die Filterleiste (Sort-Badges + Tag-Chips) als
  eigene Einheit und bettet sie auch in den Leer-Zustand ein, wenn ein
  Filter (Suche oder Tags) aktiv ist.
- Aktive Chips ohne Treffer zeigen `#tag` ohne Count (Count 0 wäre
  irreführend), im aktiven Styling.
- Leer-Meldung nennt die aktiven Filter (`Keine Ergebnisse — #arbeit`).
- Neue i18n-Keys `tag_add_hint`/`tag_remove_hint` (de/en/pt).

## Tests (TDD)

1. `sortState.test.ts` +4: `mergeChipTags` — aktive Tags ohne Treffer
   (count 0), keine Duplikate, Mischfälle.
2. Frontend-Suite: 328 Tests grün (324 + 4 neu).

## Verifikation

- [x] Tests grün, tsc + Build grün
- [x] GUI: Suche + Tag → 0 Treffer → Leer-Zustand MIT Sort-Badges und
      aktivem `#arbeit`-Chip; Abwahl bringt die Liste zurück (14)
- [ ] Push main → CI success
- [ ] Prod-Deploy durch User; Post-Deploy-Check im Browser
