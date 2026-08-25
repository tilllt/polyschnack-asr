# Change 124 — Tasks

## 1. Analyse / Root Cause (erledigt)
- [x] Lupe-Position lokalisiert (Toolbar statt boundary-Zeile)
- [x] Yjs-Suche/Ersetzen: `SegmentSearch` suchte gegen DB-`segments`, Anzeige
      hinkt (localTexts/Yjs); Replace schrieb per REST an der Anzeige vorbei
      (lokal reproduziert: Edit „Welt"→„Universum", Suche → 0 Treffer)
- [x] Cancel: BG-Align-Worker (Change 045, job=None) immun gegen `_cancelled`;
      Diar-Call blockierend ohne Nach-Prüfung; Frontend-Button nur bei
      processing/queued

## 2. Backend — Cancel für Alignment/Diarization (erledigt)
- [x] `_BG_ALIGN_CANCEL`-Set + Lock + `_align_cancelled`/`cancel_background_align`
      in service.py
- [x] `_run_align_phase`: BG-Cancel-Prüfung pro Gruppe (kein align()-Call)
- [x] BG-Worker: Cancel → Ergebnis verwerfen, `alignment=skipped`, Cache weg
- [x] `_abort_if_cancelled` nach dem Diar-Call (failed + Meldung)
- [x] cancel.py: `alignment == running|pending` → Registry + Cache-Delete →
      `cancelled: true`
- [x] Frontend: Cancel-Button auch bei `done` + alignment running/pending
- [x] Tests: `tests/test_cancel_align_diar.py` (4), Nachbar-Suiten grün,
      Gesamtsuite 985/985

## 3. Frontend — Lupe + Yjs-Suche/Ersetzen (erledigt)
- [x] Lupe aus Toolbar entfernt, in „Draggable boundaries"-Zeile (ml-auto)
- [x] SegmentList: `onDisplayChange(shown)` — Suche arbeitet gegen Anzeige
- [x] RecordingCard: `shownSegs` (Fingerprint-Guard) + `replaceRequest`-State
- [x] SegmentList: `replaceRequest`-Effect + `commitSegmentText`
      (Yjs setSegmentText / REST updateSegment)
- [x] SegmentSearch: reine UI, `onReplaceRequest`-Delegation
- [x] Tests: SegmentSearch.test.tsx (3), SegmentList.search.test.tsx (3),
      Gesamtsuite 334/334, Build grün

## 4. Verifikation (erledigt)
- [x] Browser (Dev-Instanz): genau 1 Lupe in der boundary-Zeile rechts
- [x] Browser: Edit → Suche findet neues Wort (1 Treffer statt 0)
- [x] Browser: Ersetzen wirkt sichtbar (Anzeige + Suche folgen)
- [x] Browser: Cancel-Button bei done+alignment=running sichtbar
- [x] Live-API: POST /cancel bei alignment=running → `cancelled: true`
      (vorher „no active job")

## 5. Release (offen)
- [ ] Commit + Push auf main
- [ ] CI grün (test-webapp, build-webapp, mirror-github, mirror-ghcr)
- [ ] Harbor zeigt neuen Tag
- [ ] Deploy durch User
