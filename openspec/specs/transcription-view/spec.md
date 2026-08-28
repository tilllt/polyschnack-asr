# Transcription View (GUI-Transkriptionsansicht)

## Purpose

Die Ansicht eines fertig transkribierten Recordings in der Webapp: Waveform-Playback
mit Wort-Karaoke, segmentierte Transkription mit Editier-Werkzeugen (Grenzen
verschieben, Segmente einfügen/löschen/teilen, Text und Sprecher ändern),
Suche, Segmentlängen-Wahl und Edit-Vollbild. Alles, was nach der Transkription
mit dem Text einer einzelnen Aufnahme passiert, läuft in dieser Ansicht.

## Requirements

### Req 1: Playback mit Karaoke-Synchronisation

- **Ablauf:** `RecordingCard` rendert `WaveformPlayer` (WaveSurfer 7) mit
  Server-Peaks + Audio-Preview (64-kbps-MP3, Fallback Voll-WAV). Play/Pause
  über Button oder globale Space-Taste.
- **Timing:** rAF-Sync-Loop liest `getCurrentTime()` mit 25-ms-Schwelle
  (~40 fps) — `timeupdate`-Events allein reichen nicht (HTMLMediaElement ~4/s).
  Zeit fließt via `onTimeUpdate` in `RecordingCard` (`currentTime`-State) und
  von dort in `SegmentList` (Karaoke-Markierung + Auto-Scroll).
- **Exklusivität:** `claimExclusivePlayback` — startet ein Player, pausiert er
  jeden anderen. Space-Shortcut (Capture-Modus in `App.tsx`) togglet den
  zuletzt beanspruchten Player; greift nicht in Eingabefeldern.
- **Stop-Semantik:** `decidePlayPause` — spielt er → pause (Markierung bleibt
  exakt stehen); steht er am Ende → „stay" (kein Auto-Reset auf 0); ohne
  geladenes Audio → „noop".
- **Lade-Indikator:** eigener Audio-Fetch (`readyFetch`) signalisiert echtes
  Lade-Ende; bis dahin Play-Button disabled + „Loading audio…" (`canplay`/
  `decode`/readyState sind im Peaks-Pfad unbrauchbar).
- **Transkript nach done (Change 138):** `useRecordingDetail` ist zusätzlich
  während `queued` aktiv (Poll 2 s bei queued/processing) — der Übergang
  `queued → processing → done` wird mitgenommen; nach abgeschlossener
  Transkription erscheint der Text in der offenen Karte ohne Reload.
- **Architektur:** `src/components/WaveformPlayer.tsx`, `App.tsx`
  (Space-Handler), `src/components/RecordingCard.tsx` (currentTime-State,
  `handleTimeUpdate`).

#### Scenario: Play und Stop per Space

- **Akteure:** Besitzer der Aufnahme.
- **Eingaben:** Space drücken, 2 s warten, Space drücken.
- **Ergebnis:** Playback startet; nach Stop bleibt die Markierung exakt an der
  Stopp-Position stehen (kein Sprung an den Anfang, kein Sprung nach vorne).

#### Scenario: Zweite Karte starten pausiert die erste

- **Akteure:** Besitzer mit zwei Aufnahmen.
- **Eingaben:** Play auf Karte A, dann Play auf Karte B.
- **Ergebnis:** A pausiert automatisch; nur B spielt.

### Req 2: Karaoke-Wort-Hervorhebung

- **Ablauf:** `SegmentList` rendert jedes Segment wortweise als Spans; das
  aktive Wort (zur Playback-Zeit) bekommt `karaoke-active`. Basis:
  `activeWordIndex(words, currentTime)`.
- **Lückenlosigkeit:** aktives Wort = letztes mit `start <= t` — ASR-Wort-
  Timestamps haben Lücken (w[i].end < w[i+1].start) und Überlappungen; die
  alte `isWordActive`-Logik (isoliertes Fenster) glitchte (kein Wort / zwei
  Wörter). `activeWordIndex` liefert immer genau ein Wort.
- **Vorlauf:** `KARAOKE_LEAD_S = 0.15` — der Aligner liefert 80-ms-Bins, die
  ~0.1–0.2 s nach dem akustischen Sprechbeginn liegen; mit Vorlauf erscheint
  die Markierung am Anfang des Wortes statt verspätet.
- **Confidence:** Per-Token-Confidence (CrispASR `probability`) → Ampel
  `conf-high/medium/low`; nur wenn mindestens ein Wort eine Zahl hat
  (`hasConfidence`), sonst keine Färbung.
- **Wort-Klick:** seekt zum Wort-Start (mit 280-ms-Doppelklick-Schutz; der
  Doppelklick öffnet den Edit-Modus statt Playback).
- **Wort-Klick im Timing-Tab (Change 137):** Im Timing-Tab lädt der
  Wort-Klick das Wort stattdessen in die Waveform-Detailansicht
  (30 %-Zoom + Timing-Markierung, s. Req 11) — kein Doppelklick-Edit, da
  der Timing-Tab read-only ist.
- **Architektur:** `src/karaoke.ts` (activeWordIndex, confidenceTier,
  confidenceClass, hasConfidence), `SegmentList.tsx` (Wort-Spans).

#### Scenario: Markierung wandert Wort für Wort mit

- **Akteure:** Besitzer.
- **Eingaben:** Playback starten, auf Wortgrenzen achten.
- **Ergebnis:** Die Markierung wechselt nahtlos (auch bei Timestamp-Lücken:
  vorheriges Wort bleibt aktiv) und erscheint mit dem Wort-Vorlauf am Anfang
  jedes Wortes.

### Req 3: Aktives Segment + Auto-Scroll

- **Ablauf:** `activeSegmentIndex(displaySegments, t)` liefert das Segment zur
  aktuellen Zeit (nach dem letzten Segment-Ende → letztes Segment).
- **Gegen die ANZEIGE rechnen:** `handleTimeUpdate` berechnet den Index gegen
  `displaySegments` (die aktuell gerenderte Segmentierung), nie gegen den
  React-Query-Cache — nach Grenz-Verschiebungen oder Segmentlängen-Änderung
  haben die angezeigten Segmente andere start/end als der Cache.
- **Auto-Scroll:** zentriert das aktive Wort im Transkriptions-Container
  (`container.scrollTo`, `block:"nearest"`-Ersatz via manueller
  Relativ-Rechnung). NIEMALS `scrollIntoView` — das scrollt alle scrollbaren
  Vorfahren (auch die Seite; „Stop scrollt die Seite nach unten"-Bug).
  Fallback: aktive Zeile, wenn kein aktives Wort markiert ist.
- **Architektur:** `src/karaoke.ts` (activeSegmentIndex, shouldScrollIntoView),
  `SegmentList.tsx` (Auto-Scroll-Effekt), `RecordingCard.tsx`
  (displaySegments, activeSegIdx).

#### Scenario: Langes Transkript, Playback scrollt mit

- **Akteure:** Besitzer mit 51-min-Transkript.
- **Eingaben:** Playback starten, nicht manuell scrollen.
- **Ergebnis:** Das aktive Wort bleibt ungefähr in der Mitte des sichtbaren
  Transkriptionsbereichs; die Seite selbst bewegt sich nicht.

### Req 4: Segment-Grenzen verschieben (Drag)

- **Ablauf:** Die Start-Timecodes (i > 0) sind Drag-Handles der Grenze davor
  (`onBoundaryPointerDown/Move/Up`). `PX_PER_WORD = 16` — alle 16 px
  Drag-Bewegung = 1 Wort; `moveBoundary(segments, boundaryIdx, delta)`.
- **Semantik:** delta < 0 (Marker nach oben) → die letzten |delta| Wörter von
  Segment N wandern an den Anfang von N+1; delta > 0 → die ersten delta
  Wörter von N+1 ans Ende von N. Wort für Wort, einzelne Wörter werden nie
  geteilt; Rand-Clamp (kein Segment wird leer); ohne Wort-Timestamps keine
  Bewegung.
- **Duplikat-Freiheit (Fix 2026-08-16):** beim Drag-Start wird die Basis-Liste
  eingefroren (`dragRef.baseSegments`) und jedes pointermove ruft
  `moveBoundary(baseSegments, idx, KUMULATIVES words)` auf — Schritt-Deltas
  auf der (noch alten) Prop-Liste duplizierten Wörter („Anton? Anton?").
  `currentList` im Ref wird bei jedem Schritt aktualisiert und beim Loslassen
  explizit an `onBoundaryDragEnd` übergeben (kein Closure-State).
- **Persistenz:** beim Loslassen `PUT /api/recordings/{rid}/segments`
  (ersetzt die komplette Liste, tiefe Kopie; `rec.text` neu zusammengesetzt;
  Versions-Snapshot `kind="edit"`). `handleBoundaryDragEnd` setzt
  `dragSegments` auf die Server-Antwort (NICHT null — sonst rechnet
  `resegmentByDuration` beim gesetzten `segMaxDuration` die manuelle Grenze
  wieder weg).
- **Architektur:** `src/resegment.ts` (moveBoundary, buildSeg),
  `SegmentList.tsx` (Drag-Handler, dragRef), `RecordingCard.tsx`
  (handleBoundaryMoved/DragEnd), `app/routers/segments.py`
  (`replace_segments`).

#### Scenario: Grenze ziehen verschiebt Wörter ohne Duplikate

- **Akteure:** Besitzer.
- **Eingaben:** Timecode einer Grenze 3 Wörter nach unten ziehen, loslassen.
- **Ergebnis:** Die ersten 3 Wörter des folgenden Segments hängen am Ende des
  vorigen; Gesamttext und Gesamtwortzahl unverändert; nach dem Loslassen
  gespeichert (Toast „Grenze gespeichert"), keine Duplikate, kein Rücksprung.

### Req 5: Segment-Struktur editieren (+/−/Split)

- **Ablauf:** Zwischen den Segmenten „+" im Kreis (fügt ein neues Segment
  nach i ein: gleicher Sprecher, das LETZTE Wort des vorigen wandert in das
  neue; deaktiviert ohne Wort-Timestamps). „−" vor jedem Timecode löscht
  Segment i (Wörter/Text ans vorige; bei Index 0 ans neue erste; nie unter
  1 Segment). Text-Markierung in einem Segment → Split-Modal (✂): der
  markierte Teil wird ein eigenes Segment mit wählbarem Sprecher, die Teile
  davor/danach behalten den Originalsprecher; ohne Wort-Timestamps wird die
  Zeit proportional zur Zeichenposition interpoliert.
- **Persistenz:** identisch zu Req 4 (PUT /segments, `persistSegmentList`).
- **Architektur:** `src/resegment.ts` (insertSegment, deleteSegment,
  splitSegmentAtRange), `SegmentList.tsx` (Buttons, Split-Modal,
  `selectionCharRange` — DOM-TreeWalker über Text-Nodes inkl. Trenn-Spaces),
  `RecordingCard.tsx` (handleSegmentInsert/Delete/Split).

#### Scenario: Segment einfügen

- **Akteure:** Besitzer.
- **Eingaben:** „+" zwischen Segment 0 und 1.
- **Ergebnis:** Neues Segment mit dem Sprecher von Segment 0; das letzte Wort
  von Segment 0 steht jetzt im neuen Segment; Gesamttext identisch.

#### Scenario: Segment aus Text-Markierung teilen

- **Akteure:** Besitzer.
- **Eingaben:** Wörter im Segment markieren → ✂ → Sprecher wählen → Bestätigen.
- **Ergebnis:** markierter Teil = eigenes Segment mit neuem Sprecher; Rest
  behält den Originalsprecher; Wort-Reihenfolge/Timestamps unverändert.

### Req 6: Segmentlänge wählbar (Re-Segmentierung)

- **Ablauf:** Zahlenfeld „📐 Segmentlänge" (Sekunden) über der Segmentliste.
  `resegmentByDuration(segments, maxDurationS)` teilt die Wörter in Buckets:
  Bucket endet, sobald (a) Ziel-Dauer überschritten würde ODER (b) der
  Sprecher wechselt; mindestens 1 Wort pro Bucket; start/end aus erstem/letztem
  Wort; Text = Wörter verbunden. Nur Wörter mit Timestamps werden aufgeteilt.
- **Konsistenz:** Die Anzeige (`displaySegments`) und der Export (SRT/VTT)
  nutzen dieselbe Aufteilung (Backend `service.py:resegment_by_duration` —
  identische Bucket-Logik). Eine manuell gezogene Grenze (dragSegments) hat
  Vorrang vor der Auto-Aufteilung.
- **Architektur:** `src/resegment.ts` (resegmentByDuration),
  `RecordingCard.tsx` (segMaxDuration-State, displaySegments),
  `app/service.py` (resegment_by_duration für Export).

#### Scenario: 105-s-Segment in 30-s-Buckets

- **Akteure:** Besitzer mit chunk-bedingt langem ASR-Segment.
- **Eingaben:** „30" ins Segmentlängen-Feld.
- **Ergebnis:** Anzeige zeigt Blöcke ≤ 30 s an Wortgrenzen; Sprecherwechsel
  erzwingen zusätzliche Brüche; Export nutzt dieselben Grenzen.

### Req 7: Text-Edit & Sprecher-Zuweisung

- **Ablauf:** Doppelklick auf ein Segment → Textarea (Auto-Grow auf
  Textgröße; Enter+Ctrl/Cmd = Speichern, Escape = Abbrechen, Blur = Speichern
  bei Änderung). `PATCH /api/recordings/{rid}/segments/{idx}` mit `text`
  ODER `speaker` (tiefe JSON-Kopie vor SQLAlchemy-Write, Versions-Snapshot).
- **Text-Änderung:** Wörter werden gleichverteilt über die Segment-Dauer neu
  gebaut (`w_duration = seg_duration / n_words`) — Karaoke bleibt funktions-
  fähig; Timestamps sind dann Schätzwerte, keine ASR-Werte.
- **Speaker-Änderung (Dropdown):** Klick auf den Sprecher-Namen öffnet ein
  Menü mit den erkannten Sprechern (unique aus allen Segmenten) → PATCH mit
  `speaker` nur für dieses Segment; Wörter/Timestamps bleiben unangetastet.
- **Globales Rename:** Stift-Icon neben dem Namen → Inline-Input →
  `POST /api/recordings/{rid}/speaker-rename` (`{from_speaker, to_speaker}`)
  ersetzt das Feld in ALLEN Segmenten (SRT/VTT/Exporte automatisch konsistent);
  400 wenn `from` nicht existiert.
- **Tolerantes Matching (Change 138/140):** `from_speaker` wird über die
  Sprecher-Nummer verglichen (`_speaker_key`) — `SPEAKER_01`, `SPEAKER_1`,
  `01`, `1`, `speaker_1` und Buchstaben (A→0) bezeichnen denselben Sprecher.
  Die Nummer wird VOLLSTÄNDIG geparst (kein Substring): „1" matcht nie
  „SPEAKER_11"; kaputte Labels (SPEAKER_A, SPEAKER_1X) matchen nie
  (→ 400). Segmente ohne speaker-Feld matchen nie.
- **Erzwungener Sync (Change 139):** Beim Speichern eines Text-Edits wird
  die Anzeige SOFORT auf den lokalen Edit-Stand gesetzt (optimistisches
  `onEdited` VOR dem Server-Write, inkl. neu gebauter Wortliste
  `rebuildWordsFromText` — gleichverteilt über die Segment-Zeit, ein
  Re-Align verfeinert später). Persistiert wird die KOMPLETTE Anzeige-Liste
  (voller Listen-PUT, `segments_manual=true`) — Anzeige, DB und Edit-Inhalt
  sind damit immer identisch (kein „Edit verlassen → alte Version" mehr).
  Bei Server-Fehler: Rollback auf den Stand vor dem Edit + sichtbarer
  Fehler-Toast.
- **Text/Wort-Invariante (Change 140):** Nach jeder Verarbeitungsphase gilt
  `" ".join(seg.words[].word) == seg.text` (für Segmente mit Wörtern):
  `reconcile_words_to_text` gleicht die Wortliste per LCS an den
  Segment-Text an (unveränderte Wörter behalten ihre Zeiten, fehlende
  Text-Wörter werden interpoliert, Fremdwörter entfernt; der Text ist
  unantastbar). Aufgerufen in der Align-Phase und als Sicherheitsnetz beim
  Job-Abschluss. Der Export (`resegment_by_duration`) verliert zusätzlich
  nie Text (proportionale Verteilung mit Wortgrenzen bei Desync).
- **Architektur:** `SegmentList.tsx` (Edit-Textarea, Speaker-Dropdown,
  Rename-Input), `app/routers/segments.py` (update_segment, rename_speaker).

#### Scenario: Wort korrigieren

- **Akteure:** Besitzer.
- **Eingaben:** Doppelklick auf Segment → Text ändern → Ctrl+Enter.
- **Ergebnis:** Segment-Text + Gesamttext aktualisiert; Wörter gleichverteilt
  neu getimt (Karaoke-fähig); Edit-Version gesichert.

#### Scenario: Sprecher zuweisen

- **Akteure:** Besitzer.
- **Eingaben:** Klick auf Sprecher-Name → andere erkannte Sprecherin wählen.
- **Ergebnis:** Nur dieses Segment trägt den neuen Sprecher; Wort-Timestamps
  unverändert; Toast „Sprecher gespeichert".

### Req 8: Suche im Transkript

- **Ablauf:** Such-Icon in der Karten-Kopfzeile öffnet `SegmentSearch` über
  der Liste. Treffer werden grün markiert (`search-hit`, bewusst ANDERS als
  der gelbe Karaoke-Marker); Klick auf einen Treffer springt zum Segment
  (container.scrollTo, zentriert). Plain-Text-Segmente: Regex-Highlight;
  Karaoke-Segmente: Wort-Substring-Prüfung pro Span.
- **Architektur:** `src/components/SegmentSearch.tsx`, `SegmentList.tsx`
  (highlightText, wordIsHit), `RecordingCard.tsx` (searchQuery/searchJump).

#### Scenario: Begriff finden und springen

- **Akteure:** Besitzer.
- **Eingaben:** Suchbegriff eingeben, Treffer anklicken.
- **Ergebnis:** Alle Vorkommen grün hervorgehoben; Klick zentriert das
  Treffer-Segment im Transkriptions-Container.

### Req 9: Edit-Vollbild (focusMode)

- **Ablauf:** Vollbild-Icon in der Karten-Kopfzeile macht die GANZE Karte zum
  Overlay (`fixed inset-x-0 top-0 z-[101] h-[100dvh] overflow-hidden`,
  `overflow-y-auto`): Waveform bleibt oben gepinnt, die Segmentliste füllt
  die Resthöhe (`fillHeight`). Escape schließt; `body` bekommt
  `overflow:hidden` währenddessen. Kollabierte Transkription wird beim Öffnen
  automatisch expandiert + Waveform geladen (expandedOnce), sonst zeigt der
  Vollbild nur die erste Zeile.
- **Architektur:** `RecordingCard.tsx` (focusMode-State, Escape-Listener,
  Fullscreen-Button), `SegmentList.tsx` (fillHeight-Prop).

#### Scenario: Vollbild öffnen und schließen

- **Akteure:** Besitzer.
- **Eingaben:** Vollbild-Icon, dann Escape.
- **Ergebnis:** Karte füllt den Viewport mit pin-fixierter Waveform und
  voller Transkription; Escape stellt die normale Listenansicht wieder her.

### Req 10: Wort-Timing-Invariante (übergreifend)

- **Ablauf:** Jede GUI-Operation darf nur die Segment-ZUORDNUNG der Wörter
  ändern, nie die Wörter selbst: `moveBoundary`/`insertSegment`/
  `deleteSegment`/`splitSegmentAtRange`/`resegmentByDuration` verschieben
  Wort-Objekte als Referenzen bzw. kopieren Primitive (`start`/`end`),
  Timestamps bleiben exakt erhalten. Backend-Roundtrip (PUT /segments →
  `json.loads(json.dumps(...))` → Response) erhält `words` 1:1.
- **Verifikation:** `src/resegment.test.ts` — `flattenWords(list)` vergleicht
  `word|start|end` vor/nach jeder Operation (Achtung: Segmente sind nicht
  lückenlos — teste `out[i].start >= out[i-1].end`, nicht Gleichheit).
- **Ausnahme:** Nur die Text-Edit-Operation (Req 7) baut Wörter NEU
  (gleichverteilt) — dokumentierter Trade-off, damit Karaoke nach Korrekturen
  funktioniert.
- **Ausnahme 2 (Change 137):** Die Timing-Korrektur (Req 11) ändert gezielt
  `start`/`end` genau EINES Wortes und setzt `override` — die
  `flattenWords`-Invariante gilt weiterhin für Struktur-Operationen; die
  Reihenfolge der Wörter bleibt per Clamp monoton (Lücken erlaubt).
- **Architektur:** `src/resegment.ts`, `src/resegment.test.ts`,
  `app/routers/segments.py` (replace_segments: tiefe Kopie).

#### Scenario: Alle Operationen erhalten Wort-Timestamps

- **Akteure:** Besitzer.
- **Eingaben:** Grenze ziehen, Segment einfügen, löschen, teilen,
  Segmentlänge ändern — in beliebiger Reihenfolge.
- **Ergebnis:** flattenWords (wort|start|end über alle Segmente) ist vor und
  nach jeder Operation identisch; nur die Segment-Zuordnung ändert sich.

### Req 11: Timing-Tab (Word-Timing manuell präzisieren)

- **Ablauf:** Der Editor-Bereich der RecordingCard hat zwei Tabs:
  „Transkription" (bestehender Text-Editor) und „Timing" (neu). Der
  Timing-Tab zeigt eine read-only-Wortliste/Transkription plus eine
  Waveform-Detailansicht. Klick auf ein Wort lädt das Wort in die Waveform.
- **Zoom (30 %-Regel):** Die Waveform zoomt so auf das Wort, dass dessen
  Wellenform ca. **30 % der sichtbaren Zeitspanne** belegt
  (`pps = 0.3 * Containerbreite / Wortdauer`, geclampt auf
  `MAX_TIMING_PPS`/fitPps); der Playhead springt zum Wortstart. Quelle für
  Position/Länge ist das **letzte Alignment** (aktueller
  `words[].start/end`-Stand in den Segmenten) — kein neuer Align-Lauf.
- **Markierung:** Ein Overlay über der Waveform repräsentiert das Alignment
  des geladenen Wortes: **Anfang, Ende, Länge** (Anzeige als Zeitcodes).
  Zwei Drag-Handles (Start/Ende) verändern das Wort-Timing — die manuelle
  Präzisierung überschreibt das automatische Alignment.
- **Persistenz:** onDragEnd → `PATCH /api/recordings/{rid}/segments/{idx}/words/{word_idx}`
  mit `{start, end}` (Auth, `ensure_access(write)`, Versions-Snapshot
  `kind="edit"`). Das Wort bekommt `override=true`; die Segment-Grenzen
  werden aus erstem/letztem Wort neu abgeleitet (Export/SRT/VTT konsistent).
  Fehler → sichtbarer Toast + Anzeige-Rollback; Erfolg → Toast.
- **Override entfernen:** „Reset"-Button am geladenen Wort löscht das
  Override-Flag; das Wort behält seine aktuelle Zeit bis zum nächsten
  Re-Align.
- **Re-Align-Schutz (Override):** Ein Re-Align (Change 045/046) überschreibt
  Wörter mit `override=true` nicht — ihre manuellen `start`/`end` werden nach
  dem Align-Lauf wiederhergestellt (Index-Zuordnung je Segment; bei
  abweichender Wortzahl/Textänderung wird der Override verworfen). Alle
  anderen Wörter bekommen die frisch alignten Zeiten.
- **Validierung:** `start < end`, Mindestdauer 20 ms, Monotonie gegen
  Nachbarwörter (`start_i >= end_{i-1}`, `end_i <= start_{i+1}`, Lücken
  erlaubt) — beim Drag wird geclampt, ungültige PATCHes liefern 400.
- **Deaktivierte Edit-Funktionen:** Im Timing-Tab sind alle Edit-Funktionen
  des Transkription-Tabs aus — kein Text-Edit, kein Sprecher-Edit/Rename,
  keine Segmentgrenzen verschieben, kein +/−/Split, kein Re-Segmentieren.
  Playback/Seek bleiben aktiv (Wort akustisch prüfen).
- **Architektur:** `RecordingCard.tsx` (Tabs, TimingEditor-Integration),
  `src/components/TimingEditor.tsx` (Wortliste, Marker-Overlay, Drag),
  `WaveformPlayer.tsx` (Timing-Modus: pps-Zoom), `SegmentList.tsx`
  (`readOnly`-Prop), `app/routers/segments.py` (PATCH word timing),
  `app/service.py` (Re-Align-Merge, Change-078-Zuordnung).

#### Scenario: Wort-Timing manuell korrigieren

- **Akteure:** Besitzer der Aufnahme (aligniert, `words[].start/end` vorhanden).
- **Eingaben:** Timing-Tab öffnen, Wort anklicken, Ende-Handle der Markierung
  um ~150 ms nach rechts ziehen, loslassen.
- **Ergebnis:** Waveform zeigt das Wort gezoomt (~30 % der Ansicht); die
  Markierung wächst entsprechend; nach dem Loslassen Toast „gespeichert";
  Wort hat `override=true`, Segment-Grenze (end) folgt dem letzten Wort;
  SRT/VTT nutzen die neue Zeit; kein anderer Text/Sprecher ändert sich.

#### Scenario: Override überlebt Re-Align

- **Akteure:** Besitzer mit manuell korrigiertem Wort.
- **Eingaben:** Re-Align starten, warten bis `alignment: done`.
- **Ergebnis:** Das manuell korrigierte Wort behält seine start/end; alle
  anderen Wörter des Recordings haben die frisch alignten Zeiten.

#### Scenario: Timing-Tab blockiert Text-Edits

- **Akteure:** Besitzer im Timing-Tab.
- **Eingaben:** Doppelklick auf ein Wort/Segment, Klick auf Sprecher,
  Grenz-Handle versuchen.
- **Ergebnis:** Keine Edit-Interaktion reagiert (keine Textarea, kein
  Speaker-Menü, kein Grenz-Drag); nur Wort-Klick, Playback, Seek und die
  Timing-Markierung funktionieren.

## Bekannte Abweichungen (User-Befunde 2026-08-17 — Stand nach Fix 007)

Die gemeldeten Phänomene verletzen die Requirements oben. Stand: Reproduktions-
runde abgeschlossen (Property-Tests `resegment.test.ts`/`karaoke.test.ts` +
Playwright-GUI-Tests `/opt/data/perf-prof/repro_drag_*.mjs` gegen Dev-Server,
Mock-API); Fixes aus Change Proposal 007 umgesetzt und GUI-verifiziert.
Die Einträge sind nach Beweisgrad sortiert:

1. **Grenz-Verschiebung „speichert nicht unbedingt" den neuen Status — BEHOBEN
   (Change 007, Fix 1 + 2).** Root Cause war ein Anzeige-Desync bei gesetztem
   `segMaxDuration`: Der Drag verschiebt live korrekt, der PUT speichert am
   Server korrekt (Server-Zustand + Reload zeigen die neue Grenze), aber die
   Anzeige sprang nach dem Loslassen auf den alten Stand zurück. Ursache:
   Reset-Effekt (`setDragSegments(cur => cur !== segments ? null : cur)`)
   verglich Objekt-Referenzen; `displaySegments` ist bei gesetztem
   `segMaxDuration` eine NEU berechnete Liste → `cur !== segments` immer wahr
   → Reset. Fix: Reset vergleicht die WORT-INVARIANTE (`flattenWords`), nur
   echte Neu-Inhalte (Retranscribe) verwerfen manuelle Grenzen. Zusätzlich
   PUT-Guard „letzter Drag gewinnt" (monotone Sequenznummer) gegen Race bei
   schnellen Folge-Drags. GUI-Verifikation: `repro_drag_desync.mjs` — Live
   `w0 w1 w2 w3 | w4 w5` == Server == Reload (vorher Live auf altem Stand).
2. **Karaoke-Hervorhebung springt beim Stop — BEHOBEN (Change 007, Fix 3).**
   `activeWordIndex(words, currentTime)` addierte `KARAOKE_LEAD_S=0.15` IMMER,
   auch pausiert; zudem übergab `RecordingCard` `onPlayStateChange` nie → die
   App wusste nicht, ob gespielt wird. Fix: `onPlayStateChange` verdrahtet,
   `SegmentList` rechnet mit `leadS = isPlaying ? KARAOKE_LEAD_S : 0`.
   Beleg: `karaoke.test.ts` REPRO-Test (122/122 Tests grün).
3. **Wort-Dopplungen beim Grenz-Verschieben — als Desync-Folge behoben
   (Req 4/10).** In der puren Logik nie reproduzierbar (Property-Tests:
   mehrere Grenzen, Clamp+Rückweg, resegmentierte Liste, PUT-Roundtrip — keine
   Duplikate); Verdacht war ein SICHTBARES Symptom des Reset-Desyncs (User
   zieht, Anzeige springt zurück, erneuter Drag auf anderer Basis). Mit Fix 1
   entfällt die Ursache; erneuter GUI-Test zeigt keine Dopplungen.
   Offen bleibt der Pfad „Drag während PUT noch offen" (Race) — durch
   PUT-Guard (Fix 2) abgesichert, im GUI-Test `repro_drag_race.mjs` grün
   (letzter Drag gewinnt).
4. **Wort-Timing „manchmal" kaputt (Req 10) — kein reproduzierter Pfad.**
   Die `flattenWords`-Invariante hält in allen getesteten Operationen; ein
   Timing-Bruch war nur als Folge des Desyncs (Fix 1) denkbar. Weiter
   beobachten; bei erneutem Auftreten mit frischem Repro-Material melden.
