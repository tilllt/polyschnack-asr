# Change 077: Edit-Sync, Doppelklick-Cursor, Playback-Gating, Annotation-Redesign

## Problem (User-Befunde 2026-08-21)

1. **Edit/Display-Sync verzögert:** Doppelklick → Text bearbeiten → Edit
   verlassen → Anzeige zeigt den ALTEN Text; Edit erneut öffnen → Änderungen
   sind da; erst nach mehrmaligem Hin-und-Her erscheinen sie in der Anzeige.
2. **Doppelklick-Cursor falsch:** Doppelklick öffnet den Edit-Mode, aber der
   Cursor steht nicht an der Doppelklick-Stelle, sondern irgendwo im Text —
   wer eine bestimmte Stelle bearbeiten will, muss sie erst wieder suchen.
3. **Playback-Regression:** Play ist drückbar, obwohl die Preview-Datei noch
   nicht geladen ist — der Cursor läuft über die Waveform, aber es spielt
   kein Audio.
4. **Markierungs-Regression:** Text markieren (für Split/Annotation) startet
   wieder direkt Playback — wurde schon einmal gefixt (2026-08-18), wieder da.
5. **Annotation-Redesign:** Annotationen sollen nicht mehr als riesige Liste
   unter der Transkription hängen, sondern: Markierungsfarbe im Text für das
   annotierte Segment; Klick auf die Annotation/Waveform-Markierung scrollt
   die Transkription zur Stelle; unten sichtbar ist nur die Annotation, die
   im aktuellen Scope (Playback-Fenster/Klick) liegt — samt Antworten.
   Export der Annotationen über denselben Mechanismus wie Transkriptionen.

## Ziel

- Edit speichern zeigt die Änderung **sofort** in der Anzeige (lokal
  optimistisch), Persistenz läuft im Hintergrund (API/Yjs).
- Doppelklick positioniert den Textarea-Cursor exakt an der
  Doppelklick-Stelle (Wort-Offset aus der Browser-Selection).
- Play ist nur möglich, wenn das Audio wirklich abspielbar ist
  (canPlay-Gate an ALLEN Play-Pfaden — Button, Klick, Space, Seek).
- Textmarkierung löst nie Playback aus (Regression dauerhaft geschlossen).
- Annotationen: Text-Markierung statt Liste, Scope-basiert, Export.

## Design

### Fix 1 — Optimistisches Edit-Update (SegmentList.tsx)

`shown` erweitern: lokaler `localTexts: Segment[] | null`-State, der beim
Verlassen des Edit-Mode SOFORT den neuen Text enthält:

```
shown = dragPreview ?? localTexts ?? segmentsProp
```

- `handleSave` (beide Pfade — Collab `setSegmentText` UND non-Collab
  `updateSegment`): VOR der Persistenz `setLocalTexts(updated)` setzen →
  die Anzeige zeigt die Änderung sofort; die API/Yjs-Antwort aktualisiert
  danach `segmentsProp`.
- Esc (Edit abbrechen): `setLocalTexts(null)` + `setEditingIdx(null)` —
  der alte Text bleibt, kein halber Save.
- Kollisions-Guard (`localPendingRef` + Fingerprint): Solange der eigene
  Save läuft (pending), gewinnt KEIN Prop-Wechsel mit anderem Fingerprint
  (sonst reißt ein paralleler Refetch mit dem alten DB-Stand den
  optimistischen Text wieder weg). Kommt die eigene Bestätigung
  (Prop-Fingerprint == localTexts-Fingerprint), wird localTexts
  verworfen (Prop ist die Wahrheit). Fremd-Update ohne pending (anderer
  Client/Refetch) → Fremd gewinnt ebenfalls (localTexts = null).

### Fix 2 — Doppelklick-Cursor (SegmentList.tsx)

Beim `onDoubleClick`: Browser selektiert das Wort → `selectionCharRange`
(liefert schon `{start, end}` im Segment-Text) → nach dem Fokus der
Textarea `setSelectionRange(r.start, r.end)` (bzw. Cursor an r.start,
Ende der Wort-Auswahl). Damit steht der Cursor exakt am Doppelklick-Wort.

### Fix 3 — Playback-Gating (WaveformPlayer.tsx)

**Root Cause:** WaveSurfer-Default `interact: true` startet beim Klick auf
die Waveform SOFORT Play — unabhängig vom canPlay-Gate (das nur Button,
Space-Shortcut, `seekTo` und `playPause` schützt). Die Server-Peaks
rendern die Wellenform früh (`ready`), der Audio-Decode läuft aber noch →
Klick auf die Waveform ließ den Cursor über die Peaks „laufen", ohne Ton.

**Fix:** `interact: false` in `WaveSurfer.create` + eigener
Click-Handler auf dem Container, der NUR bei `canPlayRef.current` (echter
Decode-Buffer bzw. MediaElement readyState>=3) sucht UND spielt. Ohne
canPlay passiert beim Klick nichts (kein stummer Play-Pfad). Cleanup via
`removeEventListener` im Unmount.

Damit sind ALLE Play-Pfade gated: Button (`disabled={!canPlay}`),
Space-Shortcut (`decidePlayPause` → noop), `seekTo` (Guard im Handle),
Waveform-Klick (neuer Guard). `seekToPaused` bleibt pausiert (nur Seek).

### Fix 4 — Markierung startet kein Playback (SegmentList.tsx)

- `hasActiveTextSelection()`: native Selection nicht kollabiert →
  zentraler Guard in `handleClick`, `handleWordClick` UND der
  280-ms-scheduleClick-Ausführung (der Timer kann nach dem Loslassen
  feuern, wenn die Markierung noch aktiv ist).
- Touch-Pfad: `touchSel` mit Drag über 2+ Wörter (`startWord !==
  endWord`) blockiert Playback ebenfalls.
- Der 2026-08-18-Fix saß nur im Wort-Span-Click; die ZEILEN-Ebene
  (role=button) und der Timer umgingen ihn — jetzt ist der Guard an
  allen Playback-Eintrittspunkten.

### Feature 5 — Annotation-Redesign (AnnotationThreads.tsx, RecordingCard.tsx, SegmentList.tsx)

**Text-Markierung:** Annotationen haben `segment_idx` + `char_start/end` →
SegmentList bekommt Prop `annotations`; `wordCharRanges(words)` liefert
die Char-Range JEDES Wortes; ein Wort ist annotiert, wenn sein Bereich
eine Annotation-Range überlappt. Neue CSS-Klassen `.annot-mark` (lila,
layout-neutral wie search-hit/karaoke-active/touch-sel — nur
background-color, kein Reflow) und `.annot-active` (kräftiger, aktive
Annotation im Scope). Wort-Spans werden auch gerendert, wenn nur
Annotationen existieren (bisher nur bei onSplitSegment/Confidence/aktiv).

**Klick-Kopplung:**
- Klick auf eine Text-Markierung (annotiertes Wort) → `onAnnotateJump`
  ({id, segment_idx, start_s}) — öffnet die Annotation statt Playback.
- Waveform-Marker (💬, Change 056) → `handleMarkerClick` → setzt
  `annHighlightId` + `seekToPaused`.
- RecordingCard: `onAnnotateJump` → `setAnnHighlightId(a.id)` +
  `seekToPaused(a.start_s)`.
- SegmentList-Scroll-Effekt auf `activeAnnotationId`: zentriert das
  Segment der Annotation im Viewport (analog activeIdx-Scroll).

**Scope-Anzeige (AnnotationThreads):**
- Keine endlose Liste mehr. `activeTop` = Top-Level-Annotation, deren id
  ODER deren Antwort `activeId` ist (Playback-Fenster via annHighlightId
  ODER Klick auf Waveform-/Text-Markierung ODER frisch erstellte
  Annotation). Ohne aktive Annotation: nichts wird gerendert.
- Gezeigt wird genau dieser Thread: Autor, Zeitfenster, Body (Markdown),
  Antworten (eingerückt), Edit/Delete (Autor), Antwort-Formular (write).
- `saveAnnotation` (RecordingCard): `createAnnotation` liefert die neue
  Annotation → `setAnnHighlightId(created.id)` — die frisch erstellte
  Annotation ist sofort im Scope (sonst unsichtbar).

**Export:** Button „Annotationen exportieren" (immer sichtbar, wenn
Annotationen existieren) → `.txt` via Blob-Download (gleiche Mechanik wie
Transkriptions-Export: Datei zum Speichern). Format je Top-Level-Thread:
`[0:42–0:47] Autor (Datum)`, Body (Markdown als Klartext, Mentions →
Name), eingerückte Antworten mit Autor/Datum. i18n de/en/pt.

## Nicht-Ziel

- Kein Annotation-Backend-Umbau (Modell/API bleibt: flache Liste mit
  parent_id/segment_idx/char_start/end).
- Keine Änderung an Yjs-Protokoll/Autosave-Logik (nur lokale Anzeige).
- Kein neuer Export-Typ auf dem Server (Client-Blob-Download reicht).

## Betroffene Dateien

- `webapp/frontend/src/components/SegmentList.tsx` (Fixes 1/2/4, Annotation-Markierung)
- `webapp/frontend/src/components/WaveformPlayer.tsx` (Fix 3)
- `webapp/frontend/src/components/AnnotationThreads.tsx` (Redesign Scope + Export)
- `webapp/frontend/src/components/RecordingCard.tsx` (Scope-Verdrahtung, Scroll, Export-Button)
- `webapp/frontend/src/index.css` (.annot-mark/.annot-active)
- `webapp/frontend/src/useLocale.ts` (annot_export/annot_export_hint de/en/pt)
- `webapp/frontend/src/components/SegmentList.annotate.test.tsx` (+ Tests)
- `webapp/frontend/src/components/AnnotationThreads.test.tsx` (+ Tests)
- `docs/webui.md` (Scope-Konzept + Export)

## Erfolgskriterien

- [x] Edit speichern → Anzeige zeigt den neuen Text SOFORT (ohne erneutes
      Edit-Öffnen oder Hin-und-Her) — localTexts + pending-Guard, Test grün
- [x] Doppelklick → Cursor in der Textarea am Doppelklick-Wort
      (selectionCharRange → setSelectionRange, Test grün)
- [x] Play ohne geladenes Audio: kein Pfad startet Playback (Button,
      Space, Seek, Waveform-Klick via interact:false + canPlay-Guard)
- [x] Text markieren (Split/Annotation) startet NIE Playback
      (hasActiveTextSelection-Guard in allen Pfaden, Test grün)
- [x] Annotationen: Markierungsfarbe im Text; Klick → Scroll zur Stelle +
      Annotation+Antworten unten; nur Scope-Annotation sichtbar
- [x] Export-Button lädt Annotationen als txt (gleiches Muster wie Transkriptionen)
- [x] Frontend: tsc 0, 265/265 Tests grün, Build ok
