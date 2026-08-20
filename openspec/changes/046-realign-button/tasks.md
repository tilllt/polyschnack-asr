# Tasks — Change 046: Re-Align-Trigger-Button

## Task 1: Gemeinsame Align-Funktion

- [ ] `run_align_on_segments(rec_id, segments, audio_bytes, language, job=None, progress_cb=None)`
      aus `_run_align_phase` extrahieren (gleiche Logik, Heartbeat optional)

## Task 2: Endpoint POST /api/recordings/{rid}/realign

- [ ] Auth: write-Zugriff (ensure_access), status=done nötig
- [ ] Segmente + Audio laden, VAD/Enhance/Offset wie Job
- [ ] Align via run_align_on_segments, nur Word-Timestamps ersetzen
- [ ] Versions-Guard vor Write
- [ ] Aligner down → 503 mit verständlicher Meldung
- [ ] Cancel-Flag für User-Abbruch

## Task 3: Frontend

- [ ] „Re-Align"-Button in Transkriptions-Ansicht (write-Zugriff, done)
- [ ] Lauf-Feedback (Gruppen-Zähler), Cancel-Button
- [ ] Kein Fake-Progress

## Task 4: Tests

- [ ] Backend: auth, 404, 503, Mock-Aligner-Wörter, Grenzen unverändert
- [ ] Frontend: Button sichtbar/versteckt, Klick, Feedback
- [ ] Alle bestehenden Tests grün

## Task 5: Commit + Push

- [ ] Commit mit Change-046-Referenz
- [ ] CI prüfen + melden
