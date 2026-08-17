## MODIFIED Requirements

### Requirement: Text-Edit + Sprecher (Wort-Diff erhält Timestamps)

- **Ablauf:** Doppelklick auf ein Segment → Inline-Textarea → Ctrl+Enter →
  `PATCH /api/recordings/{rid}/segments/{idx}` mit `text` (und/oder
  `speaker`). `speaker` setzt nur das Sprecher-Label (Wörter unangetastet);
  `text` baut die Wort-Timestamps neu.
- **Wort-Diff (Change 010, ersetzt Gleichverteilung):** Die neue Wortliste
  wird per Sequenz-Alignment gegen die ALTE Wortliste gebaut —
  unveränderte Wörter behalten ihre akustischen `start/end`:
  - Gleiche Wortzahl → 1:1-Mapping (Wort an Position i behält die
    Timestamps von alt[i]) — deckt „Wort korrigieren" verlustfrei ab.
  - Unterschiedliche Wortzahl → LCS-Alignment: übereinstimmende Wörter
    behalten Timestamps; eingefügte Wörter interpolieren zwischen den
    erhaltenen Nachbarn (Segment-Grenzen als Rand); gelöschte entfallen.
  - Kein Match + unterschiedliche Wortzahl → Gleichverteilung als
    Fallback (Zeile bleibt Karaoke-fähig).
- **Segment-Grenzen:** `start`/`end` des Segments bleiben unverändert.
- **Abgrenzung Req 10:** Text-Edit ändert die Wortliste per Definition —
  die flattenWords-Invariante gilt für Struktur-Operationen; der
  Text-Edit erhält stattdessen die Timestamps ALLER unveränderten
  Wörter (stärker als die frühere Gleichverteilung).
- **Architektur:** `app/routers/segments.py` (`update_segment`,
  `_align_words`), `SegmentList.tsx` (Edit-Textarea, unverändert).

#### Scenario: Wort korrigieren — Nachbar-Timestamps bleiben

- **Akteure:** Besitzer.
- **Eingaben:** Segment mit 5 Wörtern (je 1 s); das 3. Wort wird
  korrigiert (gleiche Wortzahl).
- **Ergebnis:** Alle 5 Wörter behalten ihre ursprünglichen start/end;
  nur der Wort-Text des 3. Worts ändert sich. Karaoke/Seek bleiben
  wortgenau.

#### Scenario: Wort einfügen — Nachbarn behalten, Neues interpoliert

- **Akteure:** Besitzer.
- **Eingaben:** Segment „a b c" (a[0,1) b[1,2) c[2,3)); Text wird zu
  „a x b c" (Wort x eingefügt).
- **Ergebnis:** a/b/c behalten ihre Timestamps; x erhält einen Wert
  zwischen b's Ende und a's Start (z. B. [1,2)); Reihenfolge
  chronologisch.

#### Scenario: Wort löschen — Verbleibende behalten Timestamps

- **Akteure:** Besitzer.
- **Eingaben:** Segment „a b c" (Timestamps wie oben); Text wird zu
  „a c" (b gelöscht).
- **Ergebnis:** a und c behalten ihre start/end; b entfällt — keine
  Neuverteilung der verbleibenden Wörter.

#### Scenario: Komplett anderer Text — Fallback Gleichverteilung

- **Akteure:** Besitzer.
- **Eingaben:** Segment-Text wird vollständig umformuliert (kein
  einziges altes Wort bleibt).
- **Ergebnis:** Gleichverteilung über die Segment-Dauer (Karaoke-fähig),
  Segment-Grenzen unverändert.
