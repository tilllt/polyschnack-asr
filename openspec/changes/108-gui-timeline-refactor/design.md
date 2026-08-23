# Change 108 — Design: Timeline als Source of Truth

Ergänzt proposal.md mit den Code-Belegen (Stand 23.08.2026, Repo-Stand main @ f24820d).

## Befund-Katalog (Fehlerquellen mit Beleg)

### Backend

**B1. Zwei Zeitformate werden gemischt.**
`models.py` (Segment-Schema: `start_s`/`end_s` als float), `service.py` `_shift_segments`
(Z. 89–105) schreibt je nach Datenlage `start`/`end` UND `start_ms`/`end_ms` —
drei Feldnamen für dieselbe Zeit. Jede Konvertierung/Verzweigung ist eine
Fehlerstelle (falsche Einheit, übersehene Feld-Variante).

**B2. VAD-Trim mit mehrstufiger Offset-Kompensation.**
`service.py` Z. 35–43 + Z. 297 (`VAD_TRIM_SILENCE`): `trim_silence_with_offset`
entfernt führende/trailing Stille (vad.py trimmst **nur** leading/trailing —
kein mittleres Schneiden, gut). Danach müssen ALLE Timestamps um `offset_s`
zurückgeschoben werden (`_shift_segments`). **Jede** Verarbeitungsstufe, die das
Audio transformiert (Trim, Enhance, künftig Separate), muss dieselbe
Kompensation auf Segmente UND Wörter anwenden — eine vergessene Stufe
verschiebt alles global. Der Nutzer-Verdacht „VAD verzerrt das Timing" ist
damit berechtigt, aber der Fehler liegt in der Vollständigkeit der
Kompensation, nicht im Trim selbst.

**B3. `run_llm_enhance`: `text` und `words` laufen auseinander.**
`service.py` Z. 455–476: Der LLM-optimierte Text wird proportional auf die
Segmente verteilt (`ns["text"] = ...`), die `words`-Arrays der Segmente bleiben
**unverändert** (alt). Damit stimmen Segment-Text und Wort-Timestamps nicht
mehr überein. Folge im Editor: Split/Delete-Operationen mischen alte Wörter mit
neuem Text → **Wörter verdoppeln/verschwinden** (User-Bug 1+2).

**B4. „Status B" erzeugt Wörter ohne Timestamps.**
`service.py` Z. 179–204 (Diarisation ohne Wort-Stream): Text wird **proportional
zur Segmentdauer** aufgeteilt, Wörter als `{"word": w}` **ohne Zeit** erzeugt,
`estimated: True`. Diese geschätzten Wörter tragen keine echten Align-Zeiten,
sind aber im selben `words`-Array — Anzeige/Karaoke können sie nicht sauber von
echten Timestamps unterscheiden.

**B5. Alignment läuft auf technischen Chunks, nicht auf GUI-Segmenten.**
`service.py` Z. 482–505 (`MAX_ALIGN_GROUP_S=120`, `_split_long_segment`) +
Z. 526 (`build_align_groups`): Text wird proportional auf 120-s-Chunks verteilt;
die Wort-Timestamps werden danach via `apply_aligned_words` (Z. 565) den
Original-Segmenten zugeordnet. **Nach manueller Textänderung** (Wörter
eingefügt/gelöscht) stimmt der Chunk-Text nicht mehr mit dem Audio überein →
Aligner findet nichts (bekanntes saisoncouplet-Muster: 0 Wörter) oder ordnet
falsch zu → Drift.

**B6. Segmente sind eigene Entities mit eigener Transformations-Schicht.**
Change 088: Anzeige `deriveSegments` (resegment.ts), Backend
`resegment_by_duration`, Export (SRT/VTT) — drei Stellen erzeugen/verschieben
Segmentgrenzen (`_manual`-Flags, ≤25-s-Default). Die Wort-Timestamps leben
separat. Zwei Ebenen, die bei jeder Bearbeitung neu synchronisiert werden
müssen — jede Asymmetrie erzeugt Drift.

### Frontend

**F1. Segment-Operationen arbeiten auf der ABGELEITETEN Anzeige-Liste.**
`RecordingCard.tsx` Z. 691/700: `deleteSegment(displaySegments, idx)` /
`splitSegmentAtRange(displaySegments, …)` — die Operationen selbst sind
invarianten-sauber (`resegment.ts` Z. 253/280/331: Wort-Reihenfolge + Zeiten
bleiben erhalten), aber die Basis ist die bei jeder `deriveSegments`-Berechnung
**neu gebaute** Anzeige-Liste. Autosave/Yjs (persistBase = DB-Segmente,
`RecordingCard.tsx` Z. 1314) und Anzeige laufen über getrennte Objektgraphen.

**F2. Auto-Region über die gesamte Waveform.**
`WaveformPlayer.tsx` Z. 523–529: Bei jedem Audio-Load wird
`regions.addRegion({start: 0, end: dur, drag: true, resize: true})` gesetzt —
die ungewollte Markierung über das Ganze. Gewünscht: keine Auto-Region; Region
nur manuell (Drag) oder aus gespeicherter Markierung.

**F3. Yjs/persistBase vs. Anzeige-Transformation.**
Change-102-Regel (Vorschau nie persistieren) ist implementiert
(`persistBase` = DB-Segmente, `SegmentList.tsx` Z. 19/156), aber die
Anzeige-Liste (`displaySegments`) kann durch B3/B6 vom persistBase abweichen →
Autosave persistiert Zustände, die auf einer anderen Wortbasis beruhen.

**F4. Kein Re-Prozess-Pfad.**
Es gibt keinen Mechanismus, nach Textänderung gezielt neu zu alignen/diarisieren
oder einen Teilbereich mit anderem Modell neu zu transkribieren. Der einzige
Pfad ist das globale Re-Transcribe (RecordingCard), das ALLE Settings neu
ausführt — kein „nur das, was ich geändert habe".

## Ziel-Architektur (Details zu proposal.md)

### T1. Wortliste als einzige Wahrheit
```
Word    = { id, text, start_ms: int|null, end_ms: int|null,
            confidence: float|null, source: "asr"|"aligner"|"manual"|"estimated" }
Segment = { id, speaker, words: Word[] }   // start/end ABGELEITET (min/max)
```
- **Eine** Zeiteinheit (ms, int), **ein** Feldname. Backfill für Bestand.
- `source` erlaubt UI-Markierung („geschätzt"/„manuell") und gezieltes Re-Align
  (nur `manual`/`estimated`/`untimed` Wörter im Bereich).
- Segmente ohne Wörter (nur Text, Altlast) → beim Laden einmalig in Wörter
  konvertieren (proportional, `estimated`).

### T2. Invarianten (validiert in Client-Store UND Backend-applyOps)
1. Wort-Reihenfolge = Text-Reihenfolge (Segment-Text ist IMMER `words.join(" ")`).
2. Keine Duplikate: jede Operation auf der Wortliste, nie auf Text-Strings.
3. Segment-Grenzen verschieben/±/Split/Merge ändert nur die Gruppierung,
   nie Wort-Zeiten.
4. Wort-Edit: Ersetzung erbt Zeit des ersetzten Worts; Einfügung → `untimed`
   (Zeit = Intervall zu Nachbarn als Platzhalter), markiert als „⏱ ausstehend".
5. `deleteSegment`: Wörter wandern 1:1 in den Nachbar (nie Text-Konkatenation).
6. `insertSegment`: letztes Wort wandert (heutige Regel, bleibt).

### T3. Audio-Stufen: Offset-Register statt Schneiden
- Jede Stufe (VAD-Trim, Enhance, Separate, Chunking) trägt ein
  `AudioTransform { offset_ms, scale }`; die finale Wortzeit wird IMMER über
  die Transform-Kette auf die Original-Timeline zurückgerechnet
  (`original_ms = f(stage_ms, transforms)`).
- VAD bevorzugt **nicht** trimmen: Stille nur markieren; Chunking mit
  Kontext-Overlap (z. B. ±2 s) — Wortgrenzen am Chunk-Rand bleiben stabil.

### T4. Re-Prozess-Pipeline `POST /api/recordings/{uid}/reprocess`
```
{ steps: ["vad"|"asr"|"diarize"|"align"|"punctuate"],
  range: { start_ms, end_ms } | "all",
  backend?: "ps-pk-onnx"|…,      // nur für asr
  mode: "replace" | "proposal" }  // proposal = UI zeigt Diff vor Übernahme
```
- **align**: Wörter im Bereich mit `source in (manual, estimated)` + alle
  Wörter, deren Text sich seit letztem Align änderte (dirty-Flag aus Client) →
  gegen AKTUELLEN Text alignen (Chunk = Bereich + Kontext-Overlap).
- **diarize**: neue Speaker-Grenzen im Bereich → Gruppierung neu, Wörter
  unangetastet.
- **asr** (anderes Modell): Audio-Ausschnitt transkribieren → Text im Bereich
  ersetzen (mode=proposal: Vorschau-Diff), neue Wörter mit echten Zeiten.
- **vad**: Stille im Bereich markieren (kein Löschen).
- Ausführung als Job mit ehrlichem Status (Change-095/101-Muster),
  Original-Audio bleibt Referenz (kein zerstörerisches Trim).

### T5. Waveform
- Keine Auto-Region (F2 fix): `addRegion` nur noch bei manueller Aktion
  (Drag auf der Waveform / „Markierung setzen") oder wenn eine gespeicherte
  Markierung existiert (Markierung = reprocess/export-Bereich).

### T6. UI: ein Timeline-Store
- `useTimeline(recordingId)`: lädt Wortliste + Gruppierung; alle Komponenten
  (Waveform, SegmentList, Editor, Karaoke-Highlight) lesen aus EINEM Store;
  Playback-Position eine Quelle. Keine parallelen State-Kopien.
- Yjs-CRDT über der Wortliste; `persistBase` = DB-Wortliste (Change-102-Regel
  bleibt: Vorschau-Transformationen transient, nie persistiert).
- dirty-Flags (`untimed`, `edited`) → „Re-Align ausstehend"-Badge + Button
  „Ausstehende Änderungen alignen" (T4).

## Migrationspfad (Folge-Changes)

| Phase | Inhalt | Test |
|---|---|---|
| M1 | Datenmodell: Word-Tabelle/JSON mit source/confidence; Backfill (Segmente→Wörter, ein Zeitformat) | Migrations-Test Bestandsdaten (inkl. Recording 295 saisoncouplet) |
| M2 | Backend: applyOps mit Invarianten-Validierung; llm_enhance schreibt words mit (B3-Fix) | Property-Tests: Op-Sequenzen → keine Duplikate/Lücken |
| M3 | reprocess-Pipeline (align/diarize/asr-Bereich) | Bereichs-Tests mit Testmix + Aligner |
| M4 | Frontend: Timeline-Store, Editor auf Store, Waveform ohne Auto-Region (F2) | Playwright-E2E: delete/insert/move → keine Verdopplung |
| M5 | Playback-Sync: Karaoke-Highlight + WaveSurfer aus EINER Position | Drift-Test: 10× Edit+Re-Align, Timestamps stabil ±50 ms |

## Offene Fragen

1. Yjs vs. Wortliste: Migration bestehender Yjs-Dokumente (Altdaten) nötig?
2. Sollen Segment-Speaker als Wort-Attribut oder Segment-Attribut leben
   (bei Grenz-Verschiebung wandern Wörter zwischen Speakern — Segment-Attribut
   ist einfacher, Wort-Attribut präziser)?
3. proposal-Modus für asr-Bereich: Diff-UI im Editor (v1) oder Job-Benachrichtigung?
4. Bestehen die „verdoppelten Wörter" in der DB (persistiert) oder nur in der
   Anzeige? — Vor M1 einmal mit echtem Repro-Datensatz prüfen (Bug-Repro zuerst).
