# Change 187 — Design

## Datenmodell: Die Wortliste IST der Anker

Kein neues Feld als Quelle der Wahrheit. `segment.start` / `segment.end` bleiben
persistiert (Export, Playback, Karaoke, Fremd-Clients), werden aber **abgeleitet**:

```
hat Segment Wörter:
  seg.start = words[0].start
  seg.end   = (erstes Wort des Folgesegments).start     # Grenze vor dem Wort
              bzw. words[-1].end                        # letztes Segment
ohne Wörter:
  start/end bleiben wie gespeichert (Altbestand, leerer Text)
```

Damit ist die Grenze ein **Schnitt in der globalen Wortfolge** der Aufnahme.
Verschiebt ein Re-Align die Wörter, verschiebt sich die Grenze mit — genau die
User-Anforderung. Vorbild im Bestand: `buildSeg()` in `resegment.ts` macht das
für Drag/Insert/Split schon so.

**Warum kein separates Ankerfeld** (`anchor_word_id`, `word_span`,
`boundary_after_word`): Die Segment-Wortliste existiert bereits, ist nach
Text-Edits konsistent (`reconcile_words_to_text`) und überlebt Re-Transcribe
sauber. Ein zusätzliches Index-Feld wäre eine zweite Wahrheit, die bei
Wort-Einfügungen/-Löschungen veralten kann — genau die Klasse Problem, die
Change 187 beseitigt. Ein Char-Offset-Anker (wie bei der Split-Markierung im
Frontend) wäre die Alternative; er braucht aber die Textchar-Ranges der Wörter
und bricht bei Text-Edits ohne Wörter.

## Zuordnung beim Align: Wortindex statt Zeitfenster

Der Aligner bekommt den **Gruppentext** (Konkatenation der Segment-Texte) und
liefert dessen Wörter **in Reihenfolge**. Der Code hat die Zuordnung bisher an der
Zeitachse gesucht — dabei ist sie trivial: das erste Segment der Gruppe bekommt
die ersten `len(seg.words)` Wörter, das nächste die folgenden, usw.
Messbar belegt (Recording 328): Gruppentext 242 Wörter = 33+45+42+44+78,
172 = 87+48+37; der Aligner liefert genau diese Wortzahlen zurück.

```
assign_words_by_index(group_segments, aligned_words):
    wi = 0
    for seg in group_segments:
        n = len(seg.words)
        seg.words = aligned_words[wi : wi+n]   # Texte überschreiben, Zeiten neu
        wi += n
    if wi != len(aligned_words):            # Mismatch = Fehler, kein Raten
        -> Fehlercode word_count_mismatch
```

Danach: `derive_bounds()` über alle Segmente (Abschnitt oben) und
`reconcile_words_to_text()` als unveränderte Invarianten-Bremse.

**Verworfene Alternativen**

- *Fensterzuordnung mit Toleranz/Snapping* (Wort dem Segment zuordnen, in dessen
  Zeitbereich sein Start fällt, mit Toleranzband): bleibt raten; bei Drift >20 s
  greift kein sinnvolles Band.
- *LCS über die ganze Aufnahme* (Wörter per Sequenzabgleich an den Text ziehen):
  funktioniert, ist aber unnötig — die Gruppenzuordnung ist schon eindeutig, und
  LCS entscheidet bei wiederholten Wortfolgen („Und …“) willkürlich.
- *Nur die Grenzen nachziehen, Zuordnung flicken*: behebt das Symptom des
  heutigen Falls, lässt aber die Fensterlogik und damit die Drift-Anfälligkeit
  stehen.

## Gruppen und Naht

`build_align_groups()` bildet heute Gruppen durch Aufsummieren der
Segment-Zeiten. Mit Wort-Ankern werden Gruppen aus **aufsteigenden
Wortzeit-Bereichen** gebildet; benachbarte Gruppen stoßen aneinander
(Gruppen-Schnitt = Segment-Schnitt).

An der Naht kann die Alignment der zweiten Gruppe minimal anders liegen als die
der ersten (eigener Audio-Schnitt, eigene Zeitbasis). Regel:

```
glue_group_boundary(prev_last_end, next_words):
    delta = prev_last_end - next_words[0].start
    if delta > 0: next_words += delta        # Doppelzone auflösen
    # Lücken bleiben Lücken (echte Sprechpause), aber nie rückwärts
```

Belegt am Live-Fall: Gruppe 1 endet 109,20 s, Gruppe 2 beginnt 105,08 s → 4,1 s
Doppelzone, die heute unaufgelöst in die Merge-Liste läuft.

## Status- und Fehlersemantik

| Situation | Status | Meldung |
|---|---|---|
| Aligner liefert, Wörter/ Grenzen ändern sich | `done` | „Wort-Timestamps ersetzt" |
| Aligner liefert, aber Ergebnis identisch | `done` | „schon aligniert (unverändert)" |
| Aligner liefert nicht (down/leer) | `skipped` | „Aligner lieferte kein Ergebnis" |
| Aligner liefert, Zuordnung verworfen | `failed` | Grund: `word_count_mismatch` / `text_word_invariant` |
| Angefragtes Music-Removal nicht möglich (409/down) | Job läuft, aber sichtbar | „Music-Removal nicht möglich (Grund) — auf Original alignt" |

Heute kollabieren Fall 2 und 3 in dieselbe irreführende Meldung
„Aligner lieferte keine Wort-Timestamps".

## Migration (Wortkanten-Korrektur)

- Endpoint/Aktion nur für Admins, **Dry-Run zuerst**: pro Recording ein Bericht
  (Segmente mit Delta > 0,5 s, aufgelöste Überlappungen, Segmente ohne Wörter →
  unangetastet).
- Ausführung schreibt die abgeleiteten Grenzen + `segments_manual` unverändert,
  erzeugt eine Version (`kind="edit"`, damit rückverfolgbar).
- Bewusst **keine** automatische Migration beim Boot (sie ändert redaktionelle
  Grenzen; User-Entscheidung: explizite Aktion).

## Teststrategie (TDD)

1. Pure Funktionen zuerst: `derive_bounds`, `assign_words_by_index`,
   `glue_group_boundary`, `normalize_boundaries` — Tabellen-Tests inkl. der
   heutigen Fixture (8 Segmente, 414 Wörter, Grenzen wie oben).
2. Fixture „gedriftete Grenzen": die heutigen Segmentzeiten + echte
   Aligner-Wortliste → Erwartung: **alle** Segmente mit echten Zeiten (heute 4/8).
3. Fixture „Überlappung 14,5 s": Normalisieren löst sie auf; Gruppen sind
   überlappungsfrei.
4. Statusmatrix-Tests inkl. `skipped` nur bei leerem Aligner-Ergebnis.
5. Frontend Vitest: `ensureSegmentBounds` erweitert um die Wortkanten-Invariante;
   Drag/Split/Insert unverändert grün.
6. Regression: bestehende Backend-Suite (1142 Tests) + Frontend-Suite grün.

## Verifikation an Recording 328 (Prod)

- Invarianten-Verletzungen 4/8 → 0, Überlappung 14,52 s → 0.
- 414/414 Wörter echte Zeiten; alle 8 Segmente > 10 verschiedene Wortabstände
  (heute 4 Segmente mit 1–2).
- Keine doppelten Wortzeiten (heute 43 Wörter doppelt).
- Zweiter Align-Lauf: „done, unverändert" statt skipped.

## Offene Punkte

1. Pause an der Grenze: Vorschlag „gehört zum vorherigen Segment"
   (Grenze = Start des ersten Wortes des Folgesegments). Alternative: hälftig
   teilen.
2. `pad_start`/`pad_end` (Sekunden, überleben Re-Align) als Rückzugs-Option —
   bewusst nicht in v1. Nachrüstbar ohne Schema-Bruch (JSON-Feld).
