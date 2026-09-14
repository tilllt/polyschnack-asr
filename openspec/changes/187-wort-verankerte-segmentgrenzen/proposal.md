# Change 187 — Wort-verankerte Segmentgrenzen

**Status:** Implemented (2026-09-14; alle Vorschläge von der User-Freigabe
gedeckt: Pause → vorheriges Segment, Überlappungen unmöglich, Migration als
explizite Admin-Aktion mit Dry-Run)

## Warum

User-Anforderung (2026-09-14, nach dem Realign-Fehlschlag an Recording 328):

> „Können wir nicht die Segmentgrenzen an bestimmten Wörtern festmachen statt an
> bestimmten Zeiten? Wenn die Wörter neu alignt werden, verschieben sich die
> Timestamps der Segmentgrenzen dann automatisch."

Das ist heute schon die Konvention der **Editier-UI** (`frontend/src/resegment.ts`):
`buildSeg()` setzt `start = words[0].start` / `end = words[letztes].end`,
`moveBoundary`, `insertSegment` und `splitSegmentAtRange` (Text markieren → eigenes
Segment) übersetzen die Nutzeraktion erst in einen **Wortbereich** und leiten die
Zeiten daraus ab.

Der **Align-Pfad** hält sich nicht daran: `apply_aligned_words()` (service.py)
weist die neuen Wörter **per Zeitfenster** zu (`ws >= seg.start`, `break` bei
`ws >= seg.end`) und lässt `start`/`end` unverändert. Ergebnis: die Invariante
„Grenze = Wortkante" ist gebrochen, der Align wirkt teilweise oder gar nicht.

## Befund (live, Recording 328 `ae7435ca…`, 2026-09-14)

Gemessen über die Prod-API/DB, reproduziert offline (`_run_align_phase(…,
background=True)`, ohne DB-Schreibzugriff):

1. Der Aligner **liefert**: Gruppe 0,24–119,52 s → 242 Wörter, Gruppe
   105,00–171,32 s → 172 Wörter (= 414, alle Wörter), je 1–2 s. Die
   Gruppentext-Wortzahl entspricht **exakt** der Summe der Segment-Wortzahlen
   (33+45+42+44+78 = 242 · 87+48+37 = 172).
2. Trotzdem endet der Lauf mit `alignment="skipped"` und
   `error="Re-Align ohne Effekt: Aligner lieferte keine Wort-Timestamps"` —
   irreführend, denn `_same_segments()` war True, nicht der Aligner leer.
3. Zustand danach: Segmente 0, 1, 6, 7 mit echten Zeiten, Segmente 2, 3, 4, 5
   unverändert im Gleichverteilungs-Platzhalter. Ursache: die gespeicherten
   Grenzen passen nicht zu den Alignment-Spannen (Segment 0: Ende 24,71 vs.
   letztes Wort 12,00 → −12,71 s; Segment 3 startet 17,4 s zu spät; Segment 4
   23,4 s zu spät) → falsche Wörter im Fenster → `reconcile_words_to_text`
   erkennt die Text-Wort-Invariante als verletzt (LCS < 50 %) und fällt auf
   `_distribute_words` zurück → Platzhalter bleibt stehen.
4. Segment 4 (98,10–119,52) und Segment 5 (105,00–129,87) **überlappen 14,52 s**;
   `build_align_groups` erzeugt daraus zwei überlappende Gruppen, deren
   Wortlisten mit Offset in eine Liste gemergt werden → 43 Wörter doppelt im
   Bereich 105–119,5 s.
5. Hinzu kommt eine still nicht-erfüllte Nutzerabsicht: angefragt war
   `htdemucs` (Music-Removal vor dem Align). Der Sep-Service antwortete dreimal
   `409 Separation läuft bereits (ein Job gleichzeitig)`; der Align lief ohne
   Vocals auf dem Original weiter und meldete das nur im Log
   („weiter mit Original"), nicht in der UI.

KPI Ausgangslage für dieses Recording: 4/8 Segmente verletzen die
Wortkanten-Invariante, 14,52 s Segment-Überlappung, 4/8 Segmente ohne echte
Wortzeiten.

## What Changes

(Verhaltens-Delta gegenüber dem Ist-Zustand)


1. **Grenzen sind Wortkanten, keine freien Zeiten.** Hat ein Segment Wörter,
   gilt `segment.start == words[0].start` und `segment.end == start des ersten
   Wortes des Folgesegments` (bzw. `words[-1].end` im letzten Segment). Die
   Grenze ist damit ein **Schnitt in einer globalen Wortfolge** der Aufnahme.
   Nutzer-sichtbar: nach „New word timestamps" springen die Segmentgrenzen an die
   neuen Wortzeiten — man muss keine Grenze nachziehen.
2. **Überlappungen und Lücken zwischen Segmenten sind per Konstruktion
   unmöglich** (`seg[i].end == seg[i+1].start`). Bestehende Überlappungen werden
   beim Normalisieren aufgelöst. Die Pause zwischen zwei Wörtern gehört zum
   Segment davor (Grenze sitzt am Start des ersten Wortes des Folgesegments).
3. **Re-Align ordnet Wörter per Wortindex zu** (Textreihenfolge) statt per
   Zeitfenster. Danach werden die Grenzen neu abgeleitet (Punkt 1). Ein
   `_distribute_words`-Fallback nach einem erfolgreichen Align ist kein
   Normalzustand mehr, sondern ein Fehler mit Grund und wird als solcher
   gemeldet.
4. **Gruppen überlappen nicht mehr.** Gruppen werden aus Wortschnitten gebildet;
   an der Naht zwischen zwei technischen Gruppen werden die Zeiten monoton
   verklebt (kein Rückwärtssprung, keine Doppelzone).
5. **Ehrlicher Status.** `alignment="skipped"` gibt es nur noch, wenn der Aligner
   wirklich kein Ergebnis geliefert hat. Liefert er und ändert sich nichts, wird
   das als „done, unverändert" (mit Notiz) von „failed, Zuordnung verworfen
   (Grund)" unterschieden. Angefragtes Music-Removal, das nicht laufen konnte
   (z. B. 409), wird sichtbar gemeldet statt still auf das Original
   zurückzufallen.
6. **Migration ist eine explizite Aktion.** Bestehende Recordings mit Wörtern
   können ihre Grenzen einmalig aus den Wörtern neu ableiten — Admin-Aktion mit
   Dry-Run-Bericht (betroffene Segmente, Deltas, aufgelöste Überlappungen). Kein
   automatisches Umschreiben beim Deploy; Segmente ohne Wörter bleiben
   unangetastet.
7. **Kein API-Bruch.** `start`/`end` bleiben die Felder (weiterhin persistiert,
   jetzt abgeleitet) — Export, Playback, Karaoke und Fremd-Clients ändern sich
   nicht.

## Specs-Delta

- `MODIFIED` **transcription-view** → „Segment-Grenzen verschieben (Drag)",
  „Segment-Struktur editieren (+/−/Split)", „Wort-Timing-Invariante
  (übergreifend)": Grenzen werden aus Wortkanten abgeleitet, Überlappungen sind
  unzulässig, jede Wortänderung zieht die Grenzen nach.
- `ADDED` **transcription-view** → „Re-Align-Wortzuordnung per Wortindex",
  „Gruppen-Naht ohne Doppelzone", „Ehrlicher Align-Status", „Migration:
  Grenzen aus Wörtern ableiten".
- `ADDED` **postprocessing** → „Angefragtes Music-Removal meldet Nichterfüllung".

**Archivierungs-Hinweis:** Die Live-Spec nutzt handgeschriebene
`### Req N:`-Header, darum kann der Validator die MODIFIED-Deltas beim Archiv
nicht automatisch matchen (INFO „Archive would refuse this delta …"). Die
Archivierung dieses Changes erfolgt deshalb von Hand (Live-Spec neu komponieren,
dann `changes/archive/187-…`), wie im Skill `openspec-authoring` beschrieben.

## Risiken / Trade-offs

- Grenzen sind nicht mehr frei platzierbar (kein Schnitt mitten in einer Pause
  oder innerhalb eines Wortes). Bewusst: genau diese Freiheit hat die Drift
  erzeugt. Eine Rückzugs-Option (`pad_start`/`pad_end`) ist in `design.md`
  beschrieben und bewusst **nicht** in v1.
- Die Ableitung ändert bestehende Grenzen (bei diesem Recording um bis zu
  23 s). Deshalb Dry-Run-Bericht + explizite Freigabe, kein stilles Umschreiben.
- Segmente ohne Wörter (leerer Text, Altbestand) behalten freie Zeiten — die
  Invariante gilt nur, wo es Wörter gibt.

## Aufgaben

Siehe `tasks.md`. Verifikations-KPI an Recording 328: Invarianten-Verletzungen
4/8 → 0, Überlappung 14,52 s → 0, 414/414 Wörter mit echten Zeiten (alle 8
Segmente mit >10 verschiedenen Wortabständen), kein Gleichverteilungs-Fallback,
zweiter Align-Lauf meldet „done, unverändert" statt „keine Wort-Timestamps".

## Offene Punkte (User-Entscheidung, Vorschlag steht)

1. Pause an der Grenze: gehört zum vorherigen Segment (Vorschlag, Grenze = Start
   des ersten Wortes des Folgesegments) oder hälftig geteilt?
2. Zweiter Align-Lauf ohne Änderung: `done` mit Notiz „schon aligniert"
   (Vorschlag) oder eigener Status?
