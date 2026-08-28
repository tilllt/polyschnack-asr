# Change 144: Segment löschen — „empty text"-Fehler bei langen Aufnahmen

**Status:** Archived

## Problem (User-Befund 2026-08-28, Recording 8976aa1b…)

„Wenn ich ein Segment entfernen will, sagt er ›segment 26: empty text‹".
Die DB dieser Recording enthält 50/50 Segmente **mit** Text — der Fehler
entsteht also im PUT: Die Anzeige-Ableitung (proportionale Text-Verteilung
über die Dauer, Change 102/137) erzeugt bei langen Aufnahmen (62 min,
Lücken/Gesprächspausen) Zeitfenster **ohne** Textzuweisung → leere
Anzeige-Segmente. `persistSegmentList` sendete sie an PUT /segments, und
die Backend-Invariante „kein leeres Segment" (Z. 772) lehnte mit 400 ab.

## Lösung

Leere Anzeige-Segmente werden vor dem PUT entfernt (statt den 400 zu
provozieren) — die Anzeige wird damit konsistent (keine leeren Zeilen
nach dem Speichern), die DB behält ihre Invariante, der Delete/Split/
Grenz-Drag kann nicht mehr an „empty text" scheitern.

## Betroffen

- `frontend/src/components/RecordingCard.tsx` — `persistSegmentList`
  filtert `text.trim() === ""` vor dem PUT.
