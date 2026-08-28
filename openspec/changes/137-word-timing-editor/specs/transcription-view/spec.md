## MODIFIED Requirements

### Requirement: Timing-Tab (Word-Timing manuell präzisieren)

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
  `src/components/TimingEditor.tsx` (neu: Wortliste, Marker-Overlay, Drag),
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

### Requirement: Karaoke-Wort-Hervorhebung (Wort-Klick im Timing-Tab)

- **Ergänzung (Change 137):** Der Wort-Klick (Req 2, Seek zum Wortstart mit
  280-ms-Doppelklick-Schutz) gilt im Transkription-Tab unverändert. Im
  Timing-Tab lädt der Wort-Klick das Wort stattdessen in die
  Waveform-Detailansicht (Zoom + Markierung) — kein Doppelklick-Edit, da der
  Timing-Tab read-only ist.

#### Scenario: Wort im Timing-Tab laden

- **Akteure:** Besitzer im Timing-Tab.
- **Eingaben:** Ein Wort in der Liste anklicken.
- **Ergebnis:** Die Waveform zoomt auf das Wort (30 %-Regel), die Markierung
  zeigt sein Alignment (Anfang/Ende/Länge); ein weiterer Klick auf ein anderes
  Wort lädt dieses.

### Requirement: Wort-Timing-Invariante (Ausnahme Timing-Korrektur)

- **Ergänzung (Change 137):** Die Timing-Korrektur ist die zweite dokumentierte
  Ausnahme der `flattenWords`-Invariante (neben Text-Edit, Change 010): Sie
  ändert gezielt `start`/`end` **genau eines** Wortes und setzt `override`.
  Die chronologische Reihenfolge der Wörter bleibt per Clamp monoton
  (Lücken erlaubt); alle übrigen Wörter und Struktur-Operationen sind
  unberührt.

#### Scenario: Korrektur ändert nur ein Wort

- **Akteure:** Besitzer.
- **Eingaben:** Wort 3 eines 5-Wort-Segments um 100 ms nach vorn ziehen.
- **Ergebnis:** flattenWords unterscheidet sich von der Baseline nur in
  `start/end` des Wortes 3 (+ `override`); Wort 1, 2, 4, 5 und alle anderen
  Segmente sind byte-identisch; die Reihenfolge bleibt chronologisch.
