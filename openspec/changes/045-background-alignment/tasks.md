# Tasks — Change 045: Hintergrund-Alignment

## Task 1: Modell + Serialisierung

- [ ] Recording-Feld `alignment: str = "done"` (pending|running|done|skipped)
- [ ] `_recording_to_dict` serialisiert `alignment`

## Task 2: Job-Fluss-Umbau

- [ ] `_run_align_phase`-Aufruf aus synchronem Pfad (service.py Z. 1006) entfernen
- [ ] Nach „done": `alignment = "pending"` + Hintergrund-Thread starten
- [ ] Worker: Audio laden (stored_path), VAD-Trim/Enhance wie Job, Offset-Handling
- [ ] Worker schreibt Segmente per Versions-Guard (überschreibt keine neuen)
- [ ] ALIGN_WORDS=false / Aligner down → `alignment = "skipped"` (synchron entschieden)
- [ ] Env `POLYSCHNACK_ALIGN_BACKGROUND` (Default true) für synchronen Fallback

## Task 3: UI

- [ ] Hinweis „Präzises Alignment läuft im Hintergrund…" bei alignment=running
- [ ] Kein Fake-Progress — Hinweis verschwindet bei done/skipped (Polling)

## Task 4: Tests

- [ ] Job done ohne Align-Phase (Timing/Status)
- [ ] Worker aktualisiert Segmente (Mock-Aligner)
- [ ] Versions-Guard
- [ ] Serialisierung enthält alignment
- [ ] Backend-Tests grün

## Task 5: Commit + Push

- [ ] Commit mit Change-045-Referenz
- [ ] CI prüfen + melden
