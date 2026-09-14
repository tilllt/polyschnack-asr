# Design — Change 190

## Mindestdauer

```
MIN_WORD_DURATION_S = 0.08   # 80 ms — Karaoke-Sichtbarkeit, Nutzer-Vorgabe
```

Algorithmus (`word_anchors.enforce_min_word_durations`), Eingabe bleibt
unverändert:

1. Wörter in Reihenfolge durchgehen, `cursor = start[0]`.
2. Für jedes Wort: `start = max(start, cursor)` (Monotonie), dann
   `end = max(end, start + 0.08)`.
3. `cursor = end` — das nächste Wort wird bei Bedarf auf `end` geschoben
   (kaskadierend, aber nur so weit nötig).
4. Kein Wort wird über die Segmentgrenze hinausgeschoben, wenn die Grenze
   bekannt ist (Clamp auf `seg_end`, Mindestdauer hat Vorrang bis 0 Grenze).

Warum kaskadieren statt überlappen: Überlappende Wörter brechen die
Invarianten aus Change 187 (`start ≥ voriges end`) und verfälschen die
Segmentanker.

## Zusammenspiel mit den bestehenden Schutzmechanismen

| Mechanismus | Zuständig für | Greift bei |
|---|---|---|
| `ensure_word_timings` (168) | fehlende Einzelwerte, zeitlose Wörter | `start` oder `end` fehlt |
| `resolve_zero_durations` (152) | `end == start`, ≤ 50 ms | Folgewort-Start nutzbar |
| `enforce_min_word_durations` (190) | **jedes** Wort | immer (`floor`) |

Die drei laufen in dieser Reihenfolge; 190 ist die letzte Instanz und damit die
Garantie.

## Messung „komprimierter Abschnitt" (Hypothese → Beleg)

Vorgehen: Audio der Aufnahme schneiden (Fenster der Align-Gruppe), denselben
Gruppentext direkt an `crispr-align:5099` schicken, Wortzeiten mit den
gespeicherten vergleichen.

- Sind die Direktzeiten **ebenfalls** komprimiert → Ursache im Aligner bzw. in
  der Fensterwahl; dokumentieren, Folge-Change.
- Sind die Direktzeiten **plausibel** → Ursache in unserer Zuordnung
  (`assign_words_by_index` / Offset der Gruppe) → Fix hier.

Der Befund wird mit Zahlen in `design.md` nachgetragen.

## Messung (14.09.2026, Aufnahme 328) — Befund

Fenster 145–165 s der Originaldatei, Text der Segmente 6+7 (85 Wörter) direkt an
`crispr-align:5099` (`/v1/audio/align`, `language=de`):

```
aligner: 85 Wörter in 1,37 s
  erste:  diesem 0,32 · Grund 0,56 · sieht 0,64 · man 0,80 · diese 1,68
  letzte: weiterhelfen. 23,44 · Hey, 23,60 · vielen 23,68 · Dank 23,76 · dafür. 23,76
  Spanne: 0,32 – 23,92 s  → 0,28 s/Wort (plausibel)
```

Gespeichert ist dagegen:

```
Segment 6: 48 Wörter in 4,56 s  → 0,095 s/Wort (unplausibel)
Segment 7: 37 Wörter, 157,52–170,59 s
```

**Befund:** Der Aligner verteilt die Wörter plausibel; die Kompression entsteht
in unserem Pfad (Gruppen-/Fensterzuschnitt oder Offset), nicht im Aligner.
Damit ist Hypothese H2 (unsere Zuordnung/Fensterwahl) gestützt, H1 (Aligner
komprimiert) widerlegt — der Aligner verschiebt auch das Fenster-Ende (Ausgabe
bis 23,92 s bei 20 s Fenster), was bei der Offset-Berechnung berücksichtigt
werden muss.

Nächster Schritt (eigener Change): Gruppenfenster und Offset im Align-Pfad mit
einem Instrumentierten Lauf gegen die Direktmessung prüfen; bis dahin bleibt der
komprimierte Abschnitt als bekannte Abweichung dokumentiert.
