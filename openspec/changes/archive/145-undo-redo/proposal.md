# Change 145: Undo/Redo (Option A — lokaler Stack)

**Status:** Accepted

## Problem

Versehentliche Änderungen an der Transkription (Text, Grenzen, Split,
Löschen) sind nicht rückgängig zu machen; die Server-Versions-Historie
(Change 068) existiert, aber ohne UI-Undo.

## Lösung (Option A)

- Lokaler Undo/Redo-Stack (max. 50 Snapshots) in `RecordingCard`.
- Snapshot wird NACH erfolgreicher Server-Bestätigung gepusht (kein
  Fehler-Push, kein Redo-Zweig-Verzeichnis-Fehler).
- Abgedeckte Aktionen: Delete, Split, Grenzen-Verschieben
  (RecordingCard-intern) + Edit-Modus-Exit (SegmentList → `onUndoSnapshot`).
- UI: Undo/Redo-Buttons in der Transkriptions-Kopfzeile (dezent, nur mit
  Inhalt aktiv) + Tastatur: Ctrl+Z / Ctrl+Shift+Z / Ctrl+Y (Browser-natives
  Text-Undo in Eingabefeldern bleibt unberührt).
- Redo wird durch eine neue Aktion invalidiert; Undo/Redo persistieren als
  normaler Segments-PUT (die Versions-Historie bleibt unberührt).
- Grenze (bewusst): Stack lebt nur in der Session (nach Reload weg);
  Option B (Server-gestützt) bleibt als Ausbaustufe offen.

## Tests

- tsc sauber, Vitest 379/379 grün.
