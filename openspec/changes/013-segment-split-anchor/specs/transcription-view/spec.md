## MODIFIED Requirements

### Requirement: Segment-Struktur editieren (+/−/Split mit Split-Anker)

- **Ablauf:** Zwischen den Segmenten „+" im Kreis (fügt ein neues Segment
  nach i ein: gleicher Sprecher, das LETZTE Wort des vorigen wandert in das
  neue; deaktiviert ohne Wort-Timestamps). „−" vor jedem Timecode löscht
  Segment i (Wörter/Text ans vorige; bei Index 0 ans neue erste; nie unter
  1 Segment). Text-Markierung in einem Segment → **Split-Symbol links am
  Rand auf Höhe des Markierungsbeginns** (Change 013, ersetzt das Auto-Modal):
  der markierte Teil wird ein eigenes Segment mit wählbarem Sprecher, die
  Teile davor/danach behalten den Originalsprecher; ohne Wort-Timestamps
  wird die Zeit proportional zur Zeichenposition interpoliert.
- **Split-Anker (Change 013):** Bei gültiger Markierung (nicht volle
  Segment-Selektion, nicht beim Editieren) erscheint KEIN Modal mehr —
  stattdessen ein Inline-SVG-Symbol (horizontal-split-Stil) links im
  Button-Kanal, absolut positioniert auf der Y-Höhe des Markierungsbeginns
  (`Range.getBoundingClientRect()` relativ zur Segment-Zeile). Klick auf
  das Symbol öffnet das Bestätigungs-Popover (Sprecherwahl + „Teilen")
  kontextnah; Markierung entfernen/Klick weg schließt den Anker.
- **Tablet — kein Google-Suchassistent-Popup (Change 013):** Auf
  Touch-Geräten (`pointer: coarse`) ist die native Textauswahl auf dem
  Segment-Text deaktiviert (`user-select: none`,
  `-webkit-touch-callout: none`) — das Android-Markierungsmenü (Google
  Suche/Lens) hängt an der nativen Selection-UI und erscheint damit nicht
  mehr. Die Markierung wird stattdessen EIGENES erkannt (Pointer-Events →
  Wort-Range) und als eigener CSS-Highlight auf den Wort-Spans gerendert.
  Desktop (Maus) behält die native Selektion (`selectionCharRange`
  unverändert); Doppelklick-Edit wird zusätzlich robuster, weil die native
  Wort-Selektion den Edit nicht mehr unterbrechen kann.
- **Persistenz:** identisch zu Req 4 (PUT /segments, `persistSegmentList`).
- **Architektur:** `src/resegment.ts` (insertSegment, deleteSegment,
  splitSegmentAtRange), `SegmentList.tsx` (Buttons, Split-Symbol +
  Anker-State, `selectionCharRange` — DOM-TreeWalker über Text-Nodes inkl.
  Trenn-Spaces), `RecordingCard.tsx` (handleSegmentInsert/Delete/Split).

#### Scenario: Segment einfügen

- **Akteure:** Besitzer.
- **Eingaben:** „+" zwischen Segment 0 und 1.
- **Ergebnis:** Neues Segment mit dem Sprecher von Segment 0; das letzte Wort
  von Segment 0 steht jetzt im neuen Segment; Gesamttext identisch.

#### Scenario: Segment aus Text-Markierung teilen (Symbol statt Modal)

- **Akteure:** Besitzer.
- **Eingaben:** Wörter im Segment markieren → links am Rand erscheint auf
  Höhe des Markierungsbeginns das Split-Symbol (kein zentriertes Modal) →
  Symbol anklicken → Sprecher wählen → Bestätigen.
- **Ergebnis:** markierter Teil = eigenes Segment mit neuem Sprecher; Rest
  behält den Originalsprecher; Wort-Reihenfolge/Timestamps unverändert.

#### Scenario: Tablet-Markierung ohne Google-Popup

- **Akteure:** Besitzer mit Android-Tablet.
- **Eingaben:** Wörter im Segment per Touch markieren.
- **Ergebnis:** Kein Google-Suchassistent-/Lens-Popup; die Markierung wird
  vom App-eigenen Highlight angezeigt; das Split-Symbol erscheint links.

#### Scenario: Doppelklick öffnet Edit (kein Modal-Unterbruch)

- **Akteure:** Besitzer (Desktop).
- **Eingaben:** Doppelklick auf eine Segment-Zeile.
- **Ergebnis:** Der Edit-Modus (Textarea) öffnet direkt — die native
  Wort-Selektion des Doppelklicks öffnet kein Split-Modal mehr
  (Auto-Modal entfällt durch Change 013; auf Touch zusätzlich native
  Selektion deaktiviert).
