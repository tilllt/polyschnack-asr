# Change 108 — GUI/Workflow-Refactoring: Timeline als Source of Truth

> Teil des Refactoring-Programms (openspec/refactoring-program.md): Stufe 3 —
> reprocess (M3) baut auf `run_workflow` aus Change 110; Sofort-Fixes F2/B3
> sind unabhängig und können vorab laufen.

> Status: KONZEPT (User-Auftrag 23.08.2026: „kompletter Refactoring der GUI … nochmal von vorne anfangen und überlegen, wie man es besser hinkriegt")
> Dieser Change ist ein Design-Change: Er beschreibt die Ziel-Architektur und den Migrationspfad. Umsetzung in Folge-Changes.

## Problem

Der Nutzer berichtet wiederkehrende Sync-Fehler zwischen Waveform, Karaoke-Playback/Alignment und Diarisation, die bei Bearbeitung (Segmentgrenzen verschieben, Edit-Modus, Wörter löschen/einfügen) immer wieder auftreten:

- Segment löschen → Wörter **verdoppeln** sich
- Markieren + Einfügen → Wörter **verschwinden** oder **verdoppeln** sich
- Alignment **drifft** im Verlauf einer Bearbeitungssitzung immer weiter
- Nach Textänderungen stimmen Alignments nicht mehr
- Beim Laden einer Sounddatei wird automatisch eine Markierung über die **gesamte** Waveform gesetzt (gewünscht: keine Auto-Markierung, manuell setzbar)
- Nutzer-Verdacht: VAD (Stille rauskürzen) verzerrt das Timing

## Wurzel-Analyse (Stand der Code-Lektüre, Belege folgen im design.md)

1. **Zwei Zeitformate** (`start_s`/`end_s` float + `start_ms`/`end_ms` int + rohe `start`/`end`) werden gemischt → Konvertierungs- und Verwechslungsfehler.
2. **Segmente sind eigene Entities**, keine Ableitung der Wörter: Anzeige-Resegmentierung (Change 088, `_manual`-Flags), Backend `resegment_by_duration`, Export — mehrere Stellen erzeugen/verschieben Segmentgrenzen, während die Wort-Timestamps separat leben → die beiden Ebenen laufen auseinander.
3. **Wörter ohne Timestamps** entstehen an mehreren Stellen (Diar-Status B: proportional geschätzt `estimated: True`, Re-Chunking) und vermischen sich mit echten Align-Zeiten.
4. **VAD-Trim** entfernt führende/trailing Stille; die Kompensation (`_shift_segments`) muss in JEDER Stufe (Trim/Enhance/Separate/Chunk) konsistent auf Segmente UND Wörter angewendet werden — jede Lücke erzeugt Drift.
5. **Re-Alignment nach Textänderung** ist nicht vorgesehen: Der Forced-Aligner bekommt den Chunk-Text; nach manueller Textänderung stimmt der Text nicht mehr mit dem Audio überein → Aligner liefert nichts oder falsche Zuordnung (bekanntes saisoncouplet-Problem, Change 106 adressiert Gesang, nicht Edit-Drift).
6. **Frontend-Editor**: Segment-Operationen (delete/insert/move) und Wort-Edits operieren auf abgeleiteten Strukturen; ohne Timeline-Invarianten entstehen Duplikate und Lücken.

## Ziel-Architektur

### A. Timeline als Source of Truth
- **Wortliste mit absoluten ms-Timestamps auf der Original-Audio-Timeline** ist die einzige Wahrheit.
- **Segmente sind Gruppierungen** über der Wortliste: `start_ms`/`end_ms` werden aus den Wörtern abgeleitet (min/max), `speaker` als Segment-Attribut. Kein separates Zeitfeld, das driften kann.
- Jedes Wort: `{ text, start_ms|null, end_ms|null, confidence|null, source: asr|aligner|manual|estimated }`.
- Wörter ohne Zeit (`start_ms=null`) sind explizit „untimed" (manuell eingefügt) und werden in der UI markiert; sie sind Kandidaten für Re-Align.

### B. Editor-Invarianten (Client + Server)
1. **Kein Wort existiert doppelt**: Löschen eines Segments löscht dessen Wörter genau einmal; Einfügen fügt neue Wort-Objekte ein (nie Kopien).
2. **Segment-Grenzen verschieben ändert nur Gruppenzuordnung** — Wort-Timestamps bleiben unangetastet.
3. **Text-Edit**: Wort-Ersetzung behält die Zeit des ersetzten Worts (Kopie) oder markiert neu als `manual/untimed`.
4. **Insert** erzeugt `untimed`-Wörter mit Platzhalter-Zeit (Intervall zwischen Nachbarn) → „estimated" bis Re-Align.
5. **Eine einzige Client-Operation-API** (`timeline.applyOps(ops)`) — statt verstreuter Mutationen — mit Validierung gegen die Invarianten (Dedup-, Lücken-, Reihenfolge-Check).

### C. VAD/Audio-Stufen ohne Timing-Verlust
- VAD-Trim nur als **Start-Offset-Register** (eine Zahl pro Stufe), niemals mittleres Schneiden; alle Timestamps werden final auf die Original-Timeline zurückgerechnet.
- Alternativ (besser): VAD steuert nur **Chunking mit Overlap**, das Audio bleibt ungetrimmt; Stille wird markiert, nicht entfernt.

### D. Re-Prozess-Pipeline (Kern-Wunsch)
Neuer Endpoint `POST /api/recordings/{uid}/reprocess` mit Parametern:
```
{ steps: ["vad"|"asr"|"diarize"|"align"|"punctuate"],
  range: { start_ms, end_ms } | "all",
  backend: "ps-pk-onnx"|… (nur asr),
  keep_unmodified: true (default) }
```
- **align**: nur `untimed`/`manual`-Wörter im Bereich gegen den AKTUELLEN Text neu alignen (Chunk mit Kontext-Overlap); unveränderte Wörter behalten ihre Zeit.
- **diarize**: neue Speaker-Grenzen im Bereich → Segment-Gruppierung neu (Wörter unangetastet).
- **asr (anderes Modell)**: Audio-Ausschnitt mit neuem Backend transkribieren → Text im Bereich ersetzen (mit Bestätigungs-UI „Vorschlag"), neue Wörter mit Timestamps.
- **vad**: Stille im Bereich markieren (kein Löschen).
- Jeder Schritt läuft als eigener Job mit ehrlichem Status (Change-095/101-Muster), nie blockierend; Original-Audio bleibt Referenz.

### E. Waveform
- Beim Laden: **keine** Auto-Region/Markierung. Region nur manuell (Drag auf der Waveform) oder über „Setze Markierung"-Aktion. Markierung = Bereich für Reprocess/Export.

### F. UI-Architektur
- **Ein zentraler Timeline-Store** (Wörter + Gruppierung + Playback-Position + Auswahl + dirty-Flags), aus dem sich Waveform, Karaoke-Highlight, Segmentliste und Editor ableiten. Keine parallelen State-Kopien.
- Yjs als Kollaborations-CRDT über der Wortliste; `persistBase` = DB-Wortliste; Vorschau-Transformationen (resegmentByDuration) nur als transienter Layer, nie persistiert (Change-102-Regel bleibt).

## Migrationspfad (Folge-Changes)

1. **M1 – Datenmodell**: Wortliste mit `source`/`confidence`/`untimed`; Segment-`start_ms/end_ms` werden abgeleitet (Backfill); Migration alter Bestandsdaten (Segmente mit `estimated`-Wörtern → untimed).
2. **M2 – Backend-Invarianten + Timeline-API**: `applyOps`-Endpoint, Invarianten-Validierung, Tests (Dedup/Lücken/Drift).
3. **M3 – Re-Prozess-Pipeline**: reprocess-Endpoint + Job-Queue (align/diarize/asr-Bereich).
4. **M4 – Frontend-Refactor**: Timeline-Store, Editor auf Store umstellen, Waveform ohne Auto-Region, Re-Align-Button, dirty-Wort-Markierung.
5. **M5 – Playback-Sync**: Karaoke-Highlight strikt aus Store (Wort-Zeiten), WaveSurfer-Sync über eine Position-Quelle.

## Verifikation (pro Phase)

- Invarianten-Property-Tests: beliebige Op-Sequenzen (delete/insert/move/split/merge/edit) → keine Duplikate, keine Lücken, Summe der Wortzeiten = Segmentzeiten.
- Drift-Test: 10× bearbeiten + re-align → Timestamps stabil (±50 ms) gegen Original.
- VAD an/aus → identische Wortzeiten (Offset-Kompensation korrekt).
- E2E: Segment löschen/einfügen/verschieben in Playwright → keine Wort-Verluste/-Duplikate.
