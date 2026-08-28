# Change 145 — Tasks (Undo/Redo)

## 1. Stack in RecordingCard

- [x] `undoStackRef`/`redoStackRef` (max. 50) + `segmentsRef` (aktueller
      Stand für Redo-Snapshots)
- [x] `pushUndo(snapshot)` — pusht nur nach Server-Bestätigung,
      invalidiert Redo
- [x] `applyUndoRedo(target)` — PUT + Cache-Update, Fehler-Toast

## 2. Push-Stellen

- [x] `handleBoundaryDragEnd`: nach Erfolg `pushUndo(prevSegments)`
- [x] `persistSegmentList` (Delete/Split): nach Erfolg `pushUndo(segments)`
- [x] `SegmentList.handleSave` (Edit-Exit): `onUndoSnapshot(prevShown)`
      nach Server-Bestätigung

## 3. UI + Shortcuts

- [x] Undo/Redo-Buttons in der Transkriptions-Kopfzeile (disabled ohne
      Inhalt, `Undo2`/`Redo2`-Icons, dezent)
- [x] Ctrl+Z / Ctrl+Shift+Z / Ctrl+Y (nur außerhalb von Eingabefeldern)
- [x] i18n de/en/pt

## 4. Verifikation

- [x] tsc `--noEmit` sauber, Vitest 379/379
