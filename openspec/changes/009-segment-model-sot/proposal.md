# Change Proposal 009 — Segment-Modell als Single Source of Truth

**Status:** Proposed

## Why

Change 007 hat die reproduzierten Desync-Symptome (Anzeige springt nach
Grenz-Drag bei gesetztem `segMaxDuration` zurück) punktuell behoben
(Inhalts- statt Referenz-Vergleich im Reset-Effekt, PUT-Guard). Das
**Zustandsmodell** dahinter ist aber unverändert fragil — die
Transkriptionsansicht hält Segment-Wahrheit an drei Orten:

1. **`segments`** — React-Query-Cache (Server-Wahrheit)
2. **`dragSegments`** — lokaler State (manuelle Liste nach Drag/+/−/Split)
3. **`displaySegments`** — abgeleitete Anzeige
   (`dragSegments ?? resegmentByDuration(segments, max) ?? segments`)

Die Synchronisation zwischen 2 und 1 passiert über einen Reset-Effekt
und Objekt-/Inhalts-Vergleiche; jede neue Ableitung (Karaoke,
Re-Segmentierung, Fullscreen, Suche) erzeugt neue Referenzen und damit
die nächste Bruchstelle. Die Beobachtungs-Serie des Users (Dopplungen →
Timing → Karaoke-Sprung → „speichert nicht") ist das Muster dieser
Klasse: Symptome wandern, sobald ein Pfad gefixt ist.

**Ziel (Weg B):** Es gibt genau EINE Segment-Wahrheit — das
Recording-Modell im Cache/Server. Die Anzeige ist eine reine Funktion
des Modells; manuelle Grenzen sind Teil des Modells (persistiert), kein
UI-Overlay-State. Damit existiert die Bug-Klasse strukturell nicht mehr.

## What

### 1. „Manuelle Grenzen aktiv" wird Modell-Zustand statt UI-State
- Neues, persistiertes Feld am Recording: `segments_manual: bool`
  (Default `false`). Wird `true`, sobald eine Segment-Struktur-Operation
  gespeichert wird (Grenz-Drag, +/−, Split, Re-Segmentierung mit
  fester Dauer); wird `false` bei Transcribe/Retranscribe/Restore
  (neue ASR-Segmente = Auto-Aufteilung).
- Der Server speichert das Feld mit (PUT /segments setzt es, neue
  Transkription setzt es zurück). Kein client-seitiges Rätselraten
  über „ist die Liste manuell?".

### 2. `displaySegments` wird reine Funktion, `dragSegments` entfällt
- `displaySegments = deriveSegments(segments, segMaxDuration)`:
  - `segments_manual == true` → `segments` direkt (die gespeicherte
    manuelle Aufteilung ist die Wahrheit, keine erneute
    Re-Segmentierung)
  - sonst `segments_manual == false` und `segMaxDuration != null` →
    `resegmentByDuration(segments, segMaxDuration)` (Auto-Vorschau)
  - sonst `segments`
- Kein `dragSegments`-State, kein Reset-Effekt, keine Referenz- oder
  Inhalts-Vergleiche zur Synchronisation. Die Anzeige kann nicht mehr
  vom Modell abweichen — es gibt nichts zweites zum Synchronisieren.

### 3. Drag-Preview bleibt lokal in SegmentList, Commit ist ein Cache-Update
- Während des Ziehens rechnet `SegmentList` weiter mit ihrem
  `dragRef.currentList` (existiert seit 16.08.) — die Preview ist eine
  reine Anzeige-Frage, kein globaler Zustand.
- Beim Loslassen (`onBoundaryDragEnd(next)`): **ein** optimistisches
  Cache-Update (`setQueriesData` auf `next` + `segments_manual: true`),
  PUT im Hintergrund; bei Server-Fehler Rollback auf den vorherigen
  Modell-Stand + Fehler-Toast (bestehendes `handleEdited`-Muster,
  erweitert um das Flag + Rollback). Der PUT-Guard „letzter Drag
  gewinnt" (007) bleibt für parallele PUTs.

### 4. Invarianten-Tests als Regressions-Netz (bleibt/verstärkt)
- `flattenWords`-Invariante (Req 10) über alle Operationen — bestehende
  Property-Tests + GUI-Repro-Skripte (`repro_drag_*.mjs`) bleiben als
  Verifikation; neu: Test „Anzeige == Modell nach jedem Commit"
  (kein Desync-Pfad mehr möglich).

## Changes

- **Backend:** `models.py` (+`segments_manual`), `segments.py`
  (PUT setzt Flag), `service.py` (Transcribe/Retranscribe/Restore
  setzen Flag zurück); Migration für bestehende Aufnahmen
  (`segments_manual = false`).
- **Frontend:** `RecordingCard.tsx` — `dragSegments`-State + Reset-
  Effekt entfernen; `deriveSegments` als pure Funktion; `handleEdited`
  um Flag + Rollback erweitern; `persistSegmentList`/
  `handleBoundaryDragEnd` auf optimistisches Update umstellen.
  `SegmentList.tsx` — Drag-Preview unverändert (lokal), Commit-Pfad
  gleich.
- **Tests:** Property-Tests unverändert grün; neue Unit-Tests für
  `deriveSegments` (Flag × segMaxDuration-Matrix); GUI-Tests:
  `repro_drag_desync.mjs` bleibt grün, neu „nach Reload bleibt
  segments_manual erhalten".
- **OpenSpec:** Req 4/10 Deltas in `transcription-view` (s. Spec-Datei).

## Downgrade

- Feld `segments_manual` ignorieren, `deriveSegments` wieder durch
  die alte `dragSegments ?? resegment… ?? segments`-Kaskade ersetzen;
  Reset-Effekt (Inhalts-Vergleich, Stand 007) wiederherstellen.
  Aufnahme-Migration ist additiv (Spalte kann bleiben).
