# Change 140 — Tasks (Transkription & Export verlustfrei)

## 1. Backend: Text/Wort-Invariante (Wurzel-Fix)

- [x] `segments.py`: `reconcile_words_to_text` (LCS via `_align_words`,
      Text unantastbar, override-Flags bleiben bei Matches)
- [x] `service.py` `_run_align_phase`: Reconcile nach apply + override-
      Restore (nur wenn aligned_any)
- [x] `crud.py` `update_result`: Reconcile als Sicherheitsnetz bei
      status=done + segments (nie den Job-Abschluss brechen)
- [x] Tests `test_reconcile_words.py` (5): Fremdwörter entfernt,
      fehlende Text-Wörter interpoliert, konsistent unverändert,
      override bleibt, Ohne-Wörter/Ohne-Text übersprungen

## 2. Export-Schutz (zweite Verteidigungslinie)

- [x] `service.py` `resegment_by_duration` + `_bucket_text`: bei Desync
      Segment-Text proportional (Wortgrenzen-Snap, letzter Bucket = Rest)
- [x] `resegment.ts` `resegmentByDuration` + `bucketText` identisch
- [x] Tests: test_resegment.py (+2 Desync), resegment.test.ts (+1 Desync)

## 3. Speaker-Key sauber

- [x] `_speaker_key`: vollständiges Parsen (kein Substring, kein
      Buchstaben-Fallback auf „S" von SPEAKER)
- [x] Tests: +3 („1" matcht nie „11", kaputte Labels 400, nackte „1" nur
      Sprecher 1)

## 4. Belege

- [x] ec98bfdf: Export mit 25s vorher ~5967, nachher 6978 (= vollständig);
      Reconcile 28/28 → 0/28 desyncte Segmente, Gesamttext 6978 unverändert

## 5. Suites + OpenSpec

- [x] Backend-Suite komplett (läuft)
- [x] Vitest + tsc + build (läuft/final)
- [x] OpenSpec 140 validiert, Spec-Deltas auf Live-Specs, archiviert

## 6. Commit, Push, CI

- [x] Commit(s), Push direkt auf main, CI-Watch bis success, melden
