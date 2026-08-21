# Tasks — Change 077: Edit-Sync, Doppelklick-Cursor, Playback-Gating, Annotation-Redesign

## T1 — Fix 1: Optimistisches Edit-Update (SegmentList.tsx)
- [x] `localTexts: Segment[] | null`-State; `shown = dragPreview ?? localTexts ?? segmentsProp`
- [x] handleSave (Collab + non-Collab): vor der Persistenz `setLocalTexts(updated)`
- [x] Esc/Abbrechen: `setLocalTexts(null)` + `setEditingIdx(null)` (kein halber Save)
- [x] Fremd-Update (Prop-Wechsel von außen) gewinnt: localTexts verwerfen
      (Fingerprint-Vergleich analog yjs lastSavedRef)

## T2 — Fix 2: Doppelklick-Cursor (SegmentList.tsx)
- [x] onDoubleClick: Browser-Wort-Selection → `selectionCharRange` → nach
      focus() `setSelectionRange(start, end)` auf der Textarea
- [x] Cursor-Setup NACH dem Auto-Grow (Höhe) — erst dann setSelectionRange
- [x] **Mobile-Fix 2026-08-21:** Touch-Doppeltap-Detektor (lastTouchTapRef,
      zwei Taps auf dasselbe Wort ≤350 ms) → Edit-Modus mit Cursor am Wort;
      gemeinsamer Einstieg openEditorAt(i, charStart, charEnd) für Desktop-
      und Touch-Pfad; Drag setzt Tap-Zähler zurück
- [x] Test: Touch-Doppeltap öffnet Edit mit Cursor (selectionStart 6/End 10);
      einfacher Tap und Doppeltap auf verschiedene Wörter = kein Edit
      (3 Tests, PointerEvent-Polyfill für jsdom 25)

## T3 — Fix 3: Playback-Gating (WaveformPlayer.tsx + RecordingCard.tsx)
- [x] Root Cause: WaveSurfer-Default `interact:true` startet Play direkt beim
      Waveform-Klick — umging alle canPlay-Gates. `interact:false` + eigener
      Klick-Handler prüft `canPlayRef.current` (Decode-Buffer) vor Seek+Play.
- [x] seekToPaused bleibt pausiert; seekTo (mit Play) nur bei canPlay (bestand)
- [x] Test: decidePlayPause(…, canPlay=false) → noop (bestand; Gate-Test ergänzt)

## T4 — Fix 4: Markierung startet kein Playback (SegmentList.tsx)
- [x] Zentraler Guard `hasActiveTextSelection()` in scheduleClick-Ausführung
- [x] Guard auch in handleClick/handleWordClick + Touch-Pfad (touchSel aktiv)
- [x] Test: aktive Selection → Zeilen-Klick löst kein onSeekTo aus

## T5 — Annotation-Redesign (SegmentList.tsx, AnnotationThreads.tsx, RecordingCard.tsx)
- [x] SegmentList: Props annotations/activeAnnotationId/onAnnotateJump +
      Wort-Range-Overlap (wordCharRanges) → eigene Klasse annot-mark/annot-active
- [x] CSS: .annot-mark (lila, layout-neutral) + .annot-active in index.css
- [x] Klick auf Markierung → onAnnotateJump (öffnet Annotation statt Playback)
- [x] Scroll: activeAnnotationId-Effekt zentriert das Segment im Viewport
- [x] AnnotationThreads: Scope-Modus — nur activeTop + Antworten; ohne aktive
      Annotation nichts (Export-Button bleibt)
- [x] RecordingCard: saveAnnotation setzt annHighlightId (neue Annotation sofort
      sichtbar); onAnnotateJump → setAnnHighlightId + seekToPaused;
      annotations/activeAnnotationId an SegmentList
- [x] Export: Button „Annotationen exportieren" → txt (Zeitfenster, Autor,
      Datum, Body, Antworten eingerückt) via Blob-Download; i18n de/en/pt

## T6 — Tests
- [x] AnnotationThreads.test.tsx: Scope-Modus (nur activeId sichtbar),
      Export-Format, kein-Thread-ohne-activeId + 12 bestehende
- [x] SegmentList.annotate.test.tsx: Edit-Save zeigt Text sofort (localTexts),
      Doppelklick-Cursor-Range, Markierung startet kein Playback + 3
      Touch-Doppeltap-Tests (9 Tests gesamt)
- [x] Gates: tsc --noEmit 0, npm test 268/268, npm run build ok
- [x] Backend-Vollsuite GESAMT fail=0 (proc_a7380afc38df, SUITE_EXIT=0)

## T7 — Doku
- [x] docs/webui.md: Annotation-Scope-Konzept + Export-Button dokumentiert
