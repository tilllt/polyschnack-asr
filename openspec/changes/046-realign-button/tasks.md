# Tasks — Change 046: Re-Align-Trigger-Button

## Task 1: Gemeinsame Align-Funktion

- [x] `_schedule_realign(rec_id)` in service.py: Audio von Platte laden,
      VAD-Trim/Enhance wie im Job, Alignment-Cache schreiben, Worker starten
- [x] `_run_background_align` wiederverwendet (Versions-Guard, skipped nie Fail)

## Task 2: Endpoint POST /api/recordings/{rid}/realign

- [x] Auth: write-Zugriff (ensure_access), status=done nötig (409)
- [x] Audio laden, VAD/Enhance/Offset wie Job, Cache + Worker-Start
- [x] Versions-Guard vor Write (im Worker)
- [x] Aligner deaktiviert/Audio fehlt → 503 mit verständlicher Meldung
- [x] 404 bei unbekanntem Recording
- [x] Tests `tests/test_realign.py` (4 grün)

## Task 3: Frontend

- [x] `realignRecording()` in api.ts, `useRealign()`-Hook
- [x] „Re-Align"-Button auf der Karte (done + write, disabled bei running)
- [x] Toast-Start/Fehler, kein Fake-Progress
- [x] i18n de/en/pt
- [x] Frontend-Tests (Sichtbarkeit, Read-Only, Klick) — 188 grün, tsc sauber

## Task 4: Tests

- [x] Backend: auth, 404, 409, 503
- [x] Frontend: Button sichtbar/versteckt, Klick
- [x] Alle bestehenden Tests grün (680 Backend + 188 Frontend)

## Task 5: Commit

- [ ] Commit + Push + CI prüfen
