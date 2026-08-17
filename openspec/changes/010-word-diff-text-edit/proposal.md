# Change Proposal 010 — Wort-Diff beim Text-Edit (Timestamps erhalten)

**Status:** Proposed

## Why

Bei manuellen Text-Änderungen (Wort korrigieren, Wörter hinzufügen/löschen,
weil die Transkription falsch war) wirft `update_segment` (`segments.py`
Z. 129–138) ALLE Word-Timestamps des Segments weg und verteilt die Wörter
gleichmäßig über die Segment-Dauer:

```python
text_words = new_text.split()
w_duration = seg_duration / len(text_words)
words = [{"word": w, "start": seg_start + i*w_duration, ...}]
```

Folgen:
- **Wörter hinzugefügt** → mehr Wörter auf derselben Dauer → jedes Wort
  gestaucht, auch akustisch korrekte Nachbarwörter verschieben sich.
- **Wörter gelöscht** → verbleibende Wörter werden gedehnt.
- Karaoke-Markierung wandert danach gleichmäßig statt am Sprachfluss,
  Wort-Klick-Seek springt an interpolierte Positionen, Grenz-Drag und
  Re-Segmentierung arbeiten auf künstlichen Werten.

Damit ist der Text-Edit der EINZIGE Pfad, der Word-Timestamps zerstört —
und ausgerechnet der, der bei fehlerhaften Transkripten am häufigsten
benutzt wird. Struktur-Operationen (Grenze ziehen, +/−, Split,
Segmentlänge) erhalten die Timestamps bereits exakt (Req-10-Invariante).

**Ziel:** Unveränderte Wörter behalten ihre akustischen Timestamps;
nur neue Wörter werden interpoliert, gelöschte entfallen.

## What

### Wort-Diff-Alignment in `update_segment`
Statt `new_text.split()` + Gleichverteilung wird die neue Wortliste per
Sequenz-Alignment gegen die ALTE Wortliste gebaut:

1. **Gleiche Wortzahl** (Korrektur-Fall: gleiche Position, anderes Wort
   oder gleiches Wort mit anderer Schreibweise) → 1:1-Mapping: Wort an
   Position i behält start/end von alt[i]. Deckt die häufigste Operation
   („Wort korrigieren") verlustfrei ab.
2. **Unterschiedliche Wortzahl** (hinzufügen/löschen) → LCS-Alignment
   über die Wort-Strings: übereinstimmende Wörter (gleicher Text an
   gleicher relativer Position) behalten ihre Timestamps; neu eingefügte
   Wörter werden zwischen dem End des vorherigen und dem Start des
   nächsten erhaltenen Wortes interpoliert (Segment-Grenzen als Rand);
   gelöschte Wörter entfallen.
3. **Fallback:** Kein einziges Match und unterschiedliche Wortzahl →
   bisherige Gleichverteilung (nur dann), damit die Zeile Karaoke-fähig
   bleibt.

Die Segment-Grenzen (`start`/`end` des Segments) bleiben wie bisher
unverändert — nur `words[]` wird neu aufgebaut.

### Abgrenzung (Dokumentation in Spec Req 7)
- Text-Edit ändert die Wortliste per Definition — die Req-10-Invariante
  (flattenWords identisch) gilt weiterhin NUR für Struktur-Operationen.
  Neu: „unveränderte Wörter behalten start/end" als Eigenschaft des
  Text-Edits (stärker als heutige Gleichverteilung).

## Changes

- **Geändert:** `webapp/app/routers/segments.py` (`update_segment`:
  Wort-Diff statt Gleichverteilung; Hilfsfunktion `_align_words` mit
  LCS; ausreichend dokumentiert).
- **Tests (pytest, `webapp/tests/`):**
  - Wort korrigieren (gleiche Wortzahl) → Timestamps aller Positionen
    unverändert.
  - Wort einfügen → unveränderte Wörter behalten start/end, neues Wort
    interpoliert dazwischen (Reihenfolge chronologisch).
  - Wort löschen → verbleibende Wörter behalten Timestamps.
  - Komplett anderer Text, keine Matches → Gleichverteilung (Fallback),
    Segment-Grenzen intakt.
  - `flattenWords`-Äquivalenz für die unveränderten Wörter.
- **Frontend:** keine Änderung (API-Vertrag unverändert: `{segments,
  text}`); Karaoke/Seek profitieren automatisch.
- **OpenSpec:** Req-7-Delta in `transcription-view` (s. Spec-Datei).

## Downgrade

- `_align_words` entfernen, `update_segment` zurück auf
  `new_text.split()` + Gleichverteilung (Stand vor Change 010).
