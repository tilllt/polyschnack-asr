# Change 190 — Wortzeiten: Mindestdauer erzwingen, komprimierte Align-Abschnitte aufklären

## Warum

Zwei Befunde aus dem Re-Align von Aufnahme 328 (14.09.2026, Code-Stand 187):

1. **Wörter mit Länge 0 trotz vorhandenem Schutz.** Change 152
   (`resolve_zero_durations`) leitet bei `end == start` die Dauer aus dem Start
   des Folgeworts ab — hat das Folgewort **denselben Start**, bleibt die Dauer
   0. Change 168 (`ensure_word_timings`, Mindestannahme 150 ms) greift nur bei
   **fehlenden** Werten und überschreibt vorhandene nie. Ergebnis: Wort „ist"
   bei 156,48 s mit `end == start` (Aufnahme 328, Segment 6) — in der
   Karaoke-Timeline unsichtbar, im Export nicht markierbar.
   Nutzer-Vorgabe (bestätigt): Wortlängen dürfen nie 0 sein, Untergrenze
   annehmen.
2. **Ein komprimierter Abschnitt.** Segment 6 enthält 48 Wörter in 4,56 s
   (0,095 s/Wort) — sprachlich unmöglich. Verdacht: die Wortzeiten kommen
   komprimiert vom Aligner (dessen Ausgabe für den Zulauf-Chunk), nicht aus
   der Index-Zuordnung; die Zuordnung selbst übernimmt nur die gelieferten
   Zeiten.

## Was sich ändert

- **Harte Untergrenze für Wortdauern:** neue Normalisierung
  `enforce_min_word_durations(words, floor=0.08)` — jedes Wort bekommt
  mindestens 80 ms; Reihenfolge und „nie über den Start des nächsten Wortes"
  bleiben erhalten (kaskadierendes Vorschieben statt Überlappung).
  Eingesetzt im Align-Pfad nach `resolve_zero_durations` **und** im Choke-Point
  `reconcile_words_to_text`, damit der Zustand unabhängig vom Weg stimmt.
- **Invariante:** Gespeichert wird nie ein Wort mit `end - start < 0.08 s`
  (Ausnahme: letztes Wort einer leeren Liste — kann nicht auftreten).
- **Aufklärung des komprimierten Abschnitts:** Beweis oder Widerlegung der
  Aligner-Hypothese durch Direktmessung (gleiches Audiofenster durch
  `crispr-align:5099`, Vergleich mit den gespeicherten Zeiten). Ergebnis wird
  in `design.md` festgehalten; ein Folge-Change folgt nur, wenn die Ursache
  im Aligner oder im Fenster-Zuschnitt liegt.

## Nicht Teil dieses Changes

Die Frage, ob der Aligner generell bei langen Eingaben driftet (Überhang am
Audio-Ende, früher 2,6 s), wird hier nur **gemessen**; Korrekturen daran
gehören in einen eigenen Change.
