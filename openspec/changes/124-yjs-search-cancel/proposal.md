# Change 124 — Suche/Ersetzen im Yjs-Modus + Lupe-Position + Cancel für Align/Diar

## Problem

Drei User-Befunde (2026-08-25):

1. **Lupe falsch platziert:** Das Such-Icon (Transkription durchsuchen,
   Suchen/Ersetzen) sitzt in der Karten-Toolbar — gewünscht ist es auf der
   Zeile mit „Draggable boundaries" am rechten Rand (dort, wo der User
   sucht).

2. **Suche/Ersetzen kaputt im Yjs-Modus:** Nach einer Bearbeitung im
   Kollaborations-Modus zeigt die Suche 0 Treffer für Wörter, die im Text
   stehen; „Ersetzen" tut nichts. Ursache (lokal reproduziert): Die Suche
   (`SegmentSearch`) arbeitet auf den REST-Segmenten (`segments`-Prop =
   DB-Stand), während die SegmentList den Yjs/lokal geänderten Stand
   (`shown` = dragPreview ?? localTexts ?? prop) anzeigt. Außerdem schreibt
   „Ersetzen" per REST-`updateSegment` an der Yjs-Anzeige vorbei — die
   Änderung wird vom lokalen Zustand überdeckt („passiert nichts").

3. **Laufende Tasks nicht abbrechbar (Alignment/Diarization):**
   - **Alignment** läuft seit Change 045 als Hintergrund-Worker NACH
     „done" (`_run_background_align`, `job=None`). `_cancelled(None, …)`
     → `False` — der Worker ist **immun gegen Cancel**; der
     Cancel-Endpoint findet zudem keinen Queue-Job („no active job") und
     das Frontend zeigt den Button bei `done` gar nicht.
   - **Diarization** (synchron in der Queue) ist ein blockierender
     HTTP-Call; `_cancelled` wird nur VOR der Phase geprüft (Z. 1916) —
     ein Cancel während des Calls greift erst viel später bzw. gar nicht
     sichtbar.

## Lösung

1. **Lupe:** Such-Button wandert aus der Toolbar in die
   „Segment length / Draggable boundaries"-Zeile (rechter Rand, `ml-auto`).
   `searchOpen` bleibt in RecordingCard; SegmentList rendert die Suche.

2. **Yjs-Suche/Ersetzen:**
   - `SegmentList` meldet die tatsächlich angezeigten Segmente nach oben
     (`onDisplayChange(shown)`) — die Suche arbeitet damit gegen die
     echte Anzeige (Yjs-Edits inklusive).
   - **Ersetzen läuft über die SegmentList** (`replaceRequest`-Prop):
     sie schreibt im Yjs-Modus über `setSegmentText` (Yjs-Doc → Autosave),
     im Solo-Modus über `updateSegment` — derselbe Pfad wie manuelle Edits.
     `SegmentSearch` wird zur reinen UI (Query/Replace-State + Buttons),
     Treffer zählt sie gegen die Anzeige-Segmente.

3. **Cancel für Alignment/Diarization:**
   - `_BG_ALIGN_CANCEL`-Set (thread-safe) in service.py; Cancel-Endpoint
     erkennt `alignment == running|pending` → rec_id ins Set +
     `_AlignmentCache.delete` → `cancelled: true`. `_run_align_phase`
     prüft das Set pro Gruppe (background), der BG-Worker setzt bei
     Cancel `alignment = "skipped"` und verwirft das Ergebnis.
   - `_cancelled`-Prüfung zusätzlich NACH dem Diar-Call (vor Merge/Save) —
     Cancel wirkt spätestens nach der laufenden Phase.
   - Frontend: Cancel-Button auch bei `done` + `alignment ==
     running|pending`.

## Tests (TDD)

Backend (`tests/test_cancel_align_diar.py`):
- cancel-Endpoint bei `alignment=running` → cancelled=true + rec_id im
  Cancel-Set + Cache gelöscht
- `_run_align_phase` (background, rec_id im Set) → kein align()-Call,
  Segmente unverändert
- Diar-Nachprüfung: Job mit cancel_requested → `_abort_recording` nach
  dem Diar-Call

Frontend (jest):
- SegmentList: `onDisplayChange` liefert geänderte Anzeige; `replaceRequest`
  ersetzt Text via Yjs-Pfad (setSegmentText) statt REST
- RecordingCard: Cancel-Button bei done+alignment=running; Lupe in der
  boundary-Zeile

## Verifikation

- [ ] Rot-Tests (Backend + Frontend)
- [ ] Fix Backend + Frontend
- [ ] Grün: pytest tests/ + npm test + Build
- [ ] Browser: Yjs-Edit → Suche findet neues Wort, Ersetzen wirkt in der
      Anzeige; Cancel-Button bei Alignment/Diarization sichtbar und wirksam
- [ ] Push main → CI success → Deploy durch User
