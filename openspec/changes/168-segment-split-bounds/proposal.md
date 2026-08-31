# Change 168 — Segment-Split: fehlende start/end reparieren + No-Op sichtbar

**Status:** Proposed

## Befund (2026-08-31, Recording 8976aa1b, Edit-Session)

Der User verschob/insertierte Segmentgrenzen (Untertitel-Timing) und wollte
danach in Segment ~13:13 den Teil „Der Fußweg für die … etwa eine Stunde"
als eigenes Segment abspalten:

1. **Erster Versuch: `400: segment N missing start/end`** — Die gesendete
   Segmentliste enthielt ein Segment ohne `start`/`end`. Ursache: Nach
   Drag/Insert-Operationen kann ein Segment im Frontend-Zustand ein Feld
   mit `undefined` tragen (Wort-Grenze ohne sauberes Timestamp) —
   `JSON.stringify` lässt `undefined`-Keys komplett weg, das Backend
   lehnt die Liste dann mit „missing start/end" ab. Der Rollback
   (persistSegmentList) stellt den DB-Stand wieder her.
2. **Folgeversuche: keine Fehlermeldung, nichts passiert** — Die Markierung
   umfasst das GANZE Segment (kein Rest vor/nach): `splitSegmentAtRange`
   liefert dieselbe Segmentanzahl zurück, `handleSplitSegment` bricht
   still ab (`next.length === displaySegments.length` → early return
   OHNE Meldung). Stiller Fehler — gegen User-Regel.

## Lösung

**Kern (User-Vorgabe): Wort-Invariante — jedes Wort hat immer ein Timing.**

1. **Backend `ensure_word_timings(words, seg_start, seg_end)`** (segments.py,
   pure + testbar): Wörter ohne `start`/`end` (Aligner-Lücken, Desync)
   bekommen IMMER generierte Zeiten — als REINER FALLBACK (echte Timings
   aus Aligner/ASR/manuellem Timing-Modus werden NIE überschrieben, auch
   nicht halb vorhandene: ein echtes `start` bleibt, nur das fehlende
   `end` wird ergänzt). Randbedingungen (User-Vorgabe): geschätztes `end`
   NIE über den `start` des nächsten Wortes hinaus, geschätzter `start`
   NIE vor dem `end` des vorigen Wortes (Clamp auf die Nachbarn).
   Interpolation: Lücken proportional zur Wortlänge (≈0,09 s/Zeichen,
   min. 0,15 s), lückenlos über die verfügbare Spanne.
2. **Einbau in `reconcile_words_to_text`** (nach `_align_words`) — deckt
   ALLE Pfade ab: `crud.update_result` (ASR-Ergebnis), Aligner-Job
   (service.py) und `replace_segments` (Edit-PUT). Invariante: keine
   Wörter ohne Timing speichern → Karaoke, Split, Timing-Edits und
   Segment-Reparaturen haben immer eine Basis.
3. **Frontend `ensureSegmentBounds(segs)`** (resegment.ts, pure): Segmente
   mit fehlendem/`undefined` `start`/`end` vor dem PUT reparieren
   (Wort- oder Nachbar-Fallback) — `JSON.stringify` lässt
   `undefined`-Keys weg, das Backend lehnte sonst mit 400 ab. Einbau in
   `persistSegmentList` und `handleBoundaryDragEnd`.
4. **`handleSplitSegment`: No-Op sichtbar machen** — Markierung trifft
   kein Wort oder umfasst das ganze Segment → Info-Toast (i18n
   `split_noop`, de/en/pt) statt Stille.
5. Backend-Validierung bleibt (Integrität); die Meldung ist bereits
   präzise (Segment-Index + Feld).

## Tests

- Backend `ensure_word_timings`: Lücken-Interpolation, Rand-Wörter,
  alle-ohne-TS, alle-mit-TS (unverändert), leere Liste.
- Backend: reconcile-Wörter mit Lücken → alle haben start/end.
- Frontend `ensureSegmentBounds`: start/end-Reparatur aus Wörtern,
  Nachbar-Fallback, intakte Segmente unverändert.
- Bestehende Split-/Drag-/Dedup-Tests bleiben grün.
