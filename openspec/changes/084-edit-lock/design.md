# Design — Change 084

## D1: Awareness-Erweiterung (useYjsTranscription.ts)

- `setEditingActive(active: boolean)` → `setEditingActive(idx: number | false)`;
  Feld `editing` = Segment-Index oder `false` (Initial `false`).
- Pure Funktion `editorsFromStates(states, myId)` (neu, exportiert,
  testbar ohne Yjs):
  ```ts
  // → { activeEditors: string[], editLock: { index, name } | null }
  // activeEditors: Namen aller fremden Clients mit editing !== false
  // editLock: erster fremder Client mit editing-Index (defensiv: nur
  // einer; mit Lock kann es höchstens einen geben)
  ```
- Hook: `onAwareness` nutzt `editorsFromStates`; Rückgabe erweitert um
  `editLock`.
- `setEditingActive` bleibt der Aufruf fürs eigene Flag — SegmentList
  übergibt `editingIdx` statt `editingIdx !== null`.

## D2: Sperr-Logik (SegmentList.tsx)

- `editLock`-Prop aus dem Hook (nur wenn `collabEnabled`).
- Solange `editLock` gesetzt (FREMDER Editor aktiv):
  - `onBoundaryPointerDown` → sofort `return` (keine Grenz-Verschiebung).
  - Delete-Button, Split-/Insert-Aktionen (onSplitSegment, onSegmentDelete)
    → deaktiviert.
  - Segment `editLock.index`: Edit-Start (`handleClick`-Pfad) blockiert —
    kein Öffnen der Textarea; stattdessen Lock-Anzeige.
  - Andere Segmente bleiben editierbar (Yjs-CRDT merged Segment-Texte;
    die Struktur (Wort-Gerüst) ist das Sperrobjekt).
- **Lock-Symbol + Tooltip:** kleines Schloss-Icon (lucide `Lock`,
  12–14 px) an: (a) dem fremd-editierten Segment (neben Sprecher/Text),
  (b) den Grenz-Griffen (alle, bei aktivem fremden Edit), (c) den
  deaktivierten Struktur-Buttons. Alle mit `title={`Bearbeitet von ${name}`}`
  → Hover („Rollover") zeigt den Namen. Locale-Keys: `edit_locked_by`
  („Bearbeitet von {name}") — als title-String.

## D3: Solo-Desync-Fixes (SegmentList.tsx)

- **Fix A:** `onBoundaryPointerUp` — VOR `onBoundaryDragEnd`:
  `setLocalTexts(null); localPendingRef.current = false;`. Der Drag-Commit
  (d.currentList, basiert auf `shown` inkl. lokaler Edits) ersetzt die
  Wahrheit; das Overlay kann weg → der Fingerprint-Guard kann nie hängen.
- **Fix B:** `commitSeqRef` (monotone Sequenz in SegmentList):
  - inkrementiert bei `onBoundaryPointerDown` und bei `handleSave`-Start
  - `handleSave` nach `await updateSegment`: `if (seq !== commitSeqRef.current) return;`
    → verspätete Edit-Antwort überschreibt keinen neueren Commit
    (`setEditingIdx(null)` trotzdem — der Text ist im neueren Commit).

## D4: Tests

- `editorsFromStates`: fremder Editor (editing-Index) → editLock + Name;
  eigener Client ausgeschlossen; mehrere fremde → erster gewinnt;
  editing=false/undefined zählt nicht.
- SegmentList: Grenz-Drag blockiert bei editLock; fremd-editiertes
  Segment öffnet keine Edit-Box; Delete/Split disabled.
- Regression: moveBoundary/buildSeg-Text nach Grenz-Verschiebung korrekt
  (Edit-Box-Inhalt = neue Wortverteilung).
- Bestehende Suiten (Frontend 280+, Backend) grün halten.
