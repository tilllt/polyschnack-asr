# Change 055 — „+"-Insert-Button zwischen Segmenten entfernen

## Problem

Zwischen den Segmenten der Transkriptions-Ansicht sitzt ein „+"-Button im
Kreis (Feature 2026-08-16, Mockup) zum Einfügen eines neuen Segments nach dem
vorherigen. Der **Insert-Segment-Modus** (Change 013: Text-Markierung →
„Inserir segmento"-Dialog, `splitSegmentAtRange`) deckt das Einfügen bereits
ab. Der „+"-Button ist damit redundant, verbraucht vertikalen Platz zwischen
den Zeilen und verschlechtert die Lesbarkeit der Segmentliste.

## Ziel (wörtliche User-Vorgabe, 2026-08-20)

1. **„+"-Button entfernen** — Funktion UND UI (Prop `onSegmentInsert`,
   Handler `handleSegmentInsert`, `insertSegment`-Import).
2. **Segmente enger aneinanderrücken** — die Grenz-Leiste wird zur reinen
   Hairline (Segment-Trennung) ohne Button und ohne vertikalen Zusatzplatz.
3. **„−"-Button (Segment löschen) bleibt** — unverändert vor dem Timecode.

## Architektur

- `SegmentList.tsx`: Grenz-Leiste nur noch Hairline (`h-px flex-1`), `py-0`,
  `gap`/Button/`prevHasWords` entfallen; Prop `onSegmentInsert` entfernt.
- `RecordingCard.tsx`: `handleSegmentInsert` + Prop-Übergabe + der jetzt
  unbenutzte `insertSegment`-Import entfernt.
- `resegment.ts` (`insertSegment`-Funktion selbst) bleibt für den
  Insert-Segment-Modus erhalten (Split-Pfad nutzt andere Funktionen; die
  Funktion wird dort nicht mehr referenziert, aber ist Teil des Moduls).

## Requirements

- **REQ-UI-055-01:** Kein „+"-Button mehr zwischen den Segmenten.
- **REQ-UI-055-02:** Segment-Trennung bleibt als Hairline sichtbar; Zeilen
  rücken enger zusammen (kein 18-px-Button + gap mehr).
- **REQ-UI-055-03:** „−"-Button (Löschen) unverändert funktionsfähig.
- **REQ-UI-055-04:** Insert-Funktionalität bleibt über den Insert-Segment-
  Modus (Text-Markierung) vollständig erhalten.

## Nicht-Ziele

- Keine Änderung am Insert-Segment-Modus (Split-Dialog) selbst.
- Keine Änderung an `resegment.ts`-Logik.
