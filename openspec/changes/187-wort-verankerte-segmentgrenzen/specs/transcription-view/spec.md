## MODIFIED Requirements

### Requirement: Segment-Grenzen verschieben (Drag)

- **Anker-Invariante:** Hat ein Segment Wörter, sind seine Grenzen **abgeleitet**:
  `start = words[0].start`, `end = start des ersten Wortes des Folgesegments`
  (letztes Segment: `words[-1].end`). Die Grenze ist ein Schnitt in der globalen
  Wortfolge der Aufnahme; freie Zeitwerte ohne Wortbezug gibt es nicht mehr.
- **Semantik:** Drag verschiebt weiterhin Wörter zwischen Nachbarsegmenten
  (`moveBoundary`, `buildSeg`) — dadurch verschiebt sich die Grenze, nicht die
  Wortzeiten. Nach jeder Wortänderung werden die Grenzen neu abgeleitet.
- **Überlappungs-/Lücken-Freiheit:** `seg[i].end == seg[i+1].start` gilt immer;
  die Pause zwischen zwei Wörtern gehört zum Segment davor. Überlappungen
  (heute z. B. 14,52 s bei zwei Segmenten) werden beim Normalisieren aufgelöst.
- **Segmente ohne Wörter** (leerer Text, Altbestand) behalten ihre gespeicherten
  Zeiten unverändert.
- **Architektur:** `src/resegment.ts` (moveBoundary, buildSeg,
  `ensureSegmentBounds` erweitert), Backend-Choke-Point
  `app/routers/segments.py:reconcile_words_to_text` (leitet die Grenzen zentral
  ab, nach jedem Schreibpfad).

#### Scenario: Grenze ziehen verschiebt Wörter ohne Duplikate

- **Akteure:** Besitzer.
- **Eingaben:** Timecode einer Grenze 3 Wörter nach unten ziehen, loslassen.
- **Ergebnis:** Die ersten 3 Wörter des folgenden Segments hängen am Ende des
  vorigen; Gesamttext und Gesamtwortzahl unverändert; die Grenze sitzt auf der
  Wortkante (Start des ersten Wortes des Folgesegments), Wortzeiten unverändert,
  keine Duplikate, kein Rücksprung, keine Überlappung.

#### Scenario: Re-Align verschiebt die Grenzen automatisch

- **Akteure:** Besitzer.
- **Eingaben:** „New word timestamps" auf einem korrigierten Transkript starten.
- **Ergebnis:** Nach dem Lauf liegen alle Wortzeiten akustisch neu; die
  Segmentgrenzen sind an die neuen Wortkanten gezogen (`start`/`end` jedes
  Segments = erstes/letztes Wort), ohne dass eine Grenze manuell nachgezogen
  wurde; keine Segmentüberlappung.

### Requirement: Segment-Struktur editieren (+/−/Split)

- **Semantik:** +/−/Split arbeiten wie bisher auf Wortbereichen; zusätzlich gilt
  nach jedem dieser Wege die Anker-Invariante (Grenzen = Wortkanten,
  `seg[i].end == seg[i+1].start`).
- **Ohne Wort-Timestamps:** proportionale Interpolation wie bisher; die
  Invariante greift erst, wenn Wörter existieren.
- **Architektur:** `src/resegment.ts` (insertSegment, deleteSegment,
  splitSegmentAtRange), `app/routers/segments.py` (`replace_segments` →
  `reconcile_words_to_text`).

#### Scenario: Segment aus Text-Markierung teilen

- **Akteure:** Besitzer.
- **Eingaben:** Wörter im Segment markieren → ✂ → Sprecher wählen → Bestätigen.
- **Ergebnis:** markierter Teil = eigenes Segment mit neuem Sprecher; Rest
  behält den Originalsprecher; Wort-Reihenfolge/Timestamps unverändert; beide
  Segmente grenzen lückenlos aneinander (Grenze am Start des ersten markierten
  Wortes).

#### Scenario: Text-Edit wird nach dem Align nicht wieder verworfen

- **Akteure:** Besitzer, System.
- **Eingaben:** Text in einem Segment korrigieren, danach Re-Align.
- **Ergebnis:** Die Wortliste wird per Sequenz-Abgleich an den neuen Text
  angeglichen; die Grenzen werden aus den (ggf. neu alignten) Wörtern abgeleitet;
  kein Rückfall auf eine Gleichverteilung der Wörter über die Segmentdauer,
  solange echte Wortzeiten vorliegen.

### Requirement: Wort-Timing-Invariante (übergreifend)

- **Jedes Wort hat `start` und `end`** (Change 168) — unverändert gültig.
- **Zusätzlich (neu):** Jedes Segment mit Wörtern erfüllt die Anker-Invariante
  (`start`/`end` aus den Wörtern abgeleitet) und benachbarte Segmente überlappen
  nicht. Verletzt ein Schreibpfad (ASR-Ergebnis, Align-Job, Edit-PUT, Migration)
  die Invariante, wird sie beim Persistieren korrigiert — nicht später.
- **Monotonie über Segmente:** die Wortzeiten sind über die ganze Aufnahme
  monoton; an Nähten zwischen technischen Align-Gruppen wird monoton verklebt
  (kein Rückwärtssprung, keine Doppelzone).

#### Scenario: Alle Operationen erhalten Wort-Timestamps

- **Akteure:** System.
- **Eingaben:** Align-Lauf, Edit, Split, Drag, Re-Transcribe auf einem Recording
  mit Wörtern.
- **Ergebnis:** Kein Wort verliert Timing; kein Segment hat Grenzen, die nicht
  auf einer Wortkante liegen; keine zwei Segmente überlappen; die
  Gesamtwortzahl bleibt erhalten (kein stilles Verschlucken).

## ADDED Requirements

### Requirement: Re-Align-Zuordnung per Wortindex

- **Ablauf:** Der Align-Job schickt den Gruppentext (Konkatenation der
  Segment-Texte) an den Aligner und erhält dessen Wörter in Reihenfolge.
  Die Zuordnung erfolgt **per Wortindex**: das erste Segment der Gruppe bekommt
  die ersten `len(words)` Wörter, das nächste die folgenden, usw. (Die
  Gruppentext-Wortzahl entspricht der Summe der Segment-Wortzahlen — messbar,
  z. B. 242 = 33+45+42+44+78.)
- **Nach der Zuordnung** werden die Segmentgrenzen aus den neuen Wortzeiten
  abgeleitet.
- **Weicht die Wortzahl ab** (Aligner liefert weniger/mehr Wörter als der
  Gruppentext), wird **nicht** geraten: die Zuordnung wird verworfen und der
  Lauf meldet `failed` mit Grund (`word_count_mismatch`); die bestehenden
  Timestamps bleiben stehen.
- **Architektur:** `app/service.py` (`apply_aligned_words` ersetzt durch
  `assign_words_by_index` + `derive_bounds`, `_run_align_phase`).

#### Scenario: Gedriftete Grenzen blockieren das Alignment nicht

- **Akteure:** Besitzer.
- **Eingaben:** Korrigiertes Transkript, dessen Segmentgrenzen nicht zu den
  tatsächlichen Sprechzeiten passen (Drift > 20 s), Re-Align starten.
- **Ergebnis:** Alle Segmente erhalten echte akustische Wortzeiten (nicht nur die
  zufällig passenden); die Grenzen folgen den Wörtern; der Lauf endet `done`.

#### Scenario: Wiederholter Align-Lauf ohne Änderung

- **Akteure:** Besitzer.
- **Eingaben:** Re-Align ein zweites Mal starten, ohne dass sich Text oder Audio
  geändert haben.
- **Ergebnis:** Der Lauf endet `done` mit dem Hinweis „schon aligniert
  (unverändert)" — nicht mit „Aligner lieferte keine Wort-Timestamps".

### Requirement: Gruppen-Naht ohne Doppelzone

- **Gruppenbildung:** Align-Gruppen entstehen aus aufsteigenden Wortbereichen;
  benachbarte Gruppen überlappen nicht (Gruppen-Schnitt = Segment-Schnitt).
- **Naht-Regel:** Liegt der erste Wortstart der Folgegruppe vor dem letzten
  Wortende der Vorgruppe, wird die Folgegruppe monoton verschoben
  (`delta = prev_last_end - next_first_start`), sodass keine Doppelzone und kein
  Rückwärtssprung entsteht. Echte Sprechpausen bleiben als Lücke erhalten.
- **Architektur:** `app/service.py` (`build_align_groups`,
  `glue_group_boundary`), `app/routers/segments.py`.

#### Scenario: Zwei Gruppen mit überlappender Wortliste

- **Akteure:** System.
- **Eingaben:** Zwei Gruppen, deren Wortlisten sich in einem Zeitbereich
  überschneiden (heute: 105,08–109,20 s, 43 Wörter doppelt).
- **Ergebnis:** Nach dem Align gibt es keine doppelt vergebenen Wortzeiten; die
  Wortfolge ist über die ganze Aufnahme monoton.

### Requirement: Ehrlicher Align-Status

- **Status-Wahrheit:** `alignment="skipped"` erscheint ausschließlich, wenn der
  Aligner kein Ergebnis geliefert hat (Service down, leere Antwort). Hat der
  Aligner geliefert, aber es ändert sich nichts, lautet das Ergebnis `done` mit
  Notiz „unverändert". Konnte das Ergebnis nicht angewendet werden, ist es
  `failed` mit Grund (`word_count_mismatch`, `text_word_invariant`).
- **Nichterfüllte Nutzerabsicht wird sichtbar:** Konnte ein angefragtes
  Music-Removal (`separate_backend`) nicht laufen (z. B. 409 „Separation läuft
  bereits"), meldet die UI das („Music-Removal nicht möglich — auf Original
  alignt") statt still auf das Original zurückzufallen.
- **Architektur:** `app/service.py` (`_background_align`), `app/routers/
  segments.py` (realign-Response), Frontend-Toast-Texte (i18n).

#### Scenario: Aligner liefert, Ergebnis unverändert

- **Akteure:** Besitzer.
- **Eingaben:** Re-Align auf einem bereits alignten Recording.
- **Ergebnis:** Status `done`, Notiz „unverändert"; die Meldung „Aligner lieferte
  keine Wort-Timestamps" erscheint nicht.

#### Scenario: Music-Removal nicht möglich

- **Akteure:** Besitzer.
- **Eingaben:** Re-Align mit BGM-Entfernung, während der Separations-Service
  bereits einen Job fährt (HTTP 409).
- **Ergebnis:** Sichtbarer Hinweis, dass ohne Music-Removal alignt wurde
  (inkl. Grund), Align-Ergebnis trotzdem angewendet.

### Requirement: Migration — Grenzen aus Wörtern ableiten

- **Explizite Aktion** (Admin) analog zu Dry-Run/Apply-Mustern: liefert zuerst
  einen Bericht (Recordings, Segmente mit Delta > 0,5 s, aufgelöste
  Überlappungen, Segmente ohne Wörter), schreibt erst auf Freigabe.
- **Wirkung:** Grenzen werden auf Wortkanten gezogen, Überlappungen aufgelöst,
  `text`/Wortlisten unverändert; je Recording ein Versions-Snapshot
  (`kind="edit"`). Segmente ohne Wörter bleiben unangetastet.
- **Kein automatisches Umschreiben** beim Deploy oder Boot.
- **Architektur:** neuer Admin-Endpoint in `app/routers/admin.py` +
  Helper `app/routers/segments.py:derive_bounds`, Skript unter
  `webapp/scripts/`.

#### Scenario: Dry-Run vor dem Schreiben

- **Akteure:** Admin.
- **Eingaben:** Migrationsaktion mit `dry_run=true` für ein Recording mit
  gedrifteten Grenzen (z. B. 4 von 8 Segmenten).
- **Ergebnis:** Bericht mit Segment-Indizes, Deltas und aufgelösten
  Überlappungen; Datenbank unverändert (Nachprüfung über `updated_at` und
  Segmentzeiten).

#### Scenario: Anwenden der Migration

- **Akteure:** Admin.
- **Eingaben:** Migrationsaktion ohne `dry_run`.
- **Ergebnis:** Grenzen liegen auf Wortkanten, keine Überlappung mehr, neue
  Version in der Versionsliste; Gesamttext und Wortzahl unverändert.
