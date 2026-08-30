# Change 157 — Diar-Fehler degradieren statt Run abbrechen

**Status:** Proposed

## Befund (2026-08-30, User-Anforderung)

Ein ASR-Run darf **nie** abbrechen, weil der Diar-Container nicht läuft —
unabhängig davon, ob Diarization gewählt war:

1. **Ohne diarize-Option** kontaktiert `process_recording` den Diar-Service
   bereits nicht (`if enable_diarize:` — Code-Befund). Diese Invariante hat
   aber **keinen Test** — eine spätere Änderung könnte sie brechen.
2. **Mit diarize-Option + Diar-Container down** (live während des
   CrispASR-Image-Incidents): `DiarizationError` (service-unreachable) wurde
   im inneren Block re-raised (`except DiarizationError: raise`) und im
   äußeren Catch zu `status="failed"` → **die fertige Transkription wurde
   verworfen**, obwohl der ASR-Teil erfolgreich war.

## Lösung: Degradierung + Invarianten-Test

### Backend (app/service.py, process_recording)
1. Innerer `except DiarizationError` re-raised **nicht mehr** — stattdessen:
   `diar = None`, `diar_error = exc_d.message`, `log.warning(...)`.
2. Nach `crud.update_result`: bei `status == "done" and diar_error` →
   `rec.diar_status = "failed"` + `rec.error = diar_error[:500]` (ehrlicher,
   sichtbarer Hinweis auf der Karte; Run bleibt done).
3. Der äußere `except DiarizationError` (status=failed) bleibt als
   Sicherheitsnetz für unerwartete Pfade (z.B. Fehler VOR dem diarize-Block).

### Frontend (RecordingCard)
4. Bei `status == "done" && diar_status == "failed"`: dezentes Warn-Badge
   („Diarization fehlgeschlagen") mit `title=rec.error` — kein stummer
   Fehler (User-Regel).

### Tests (webapp/tests/test_diar_degrades_transcribe.py)
5. **Invariante:** `enable_diarize=False` → `app.diarize.diarize` wird
   **nie** aufgerufen (Mock wirft AssertionError bei Aufruf); Run wird done.
6. **Degradierung:** `enable_diarize=True` + `diarize()` wirft
   `DiarizationError("service-unreachable")` → Status done, Text+Segmente
   persistiert, `diar_status=="failed"`, `error` enthält die Meldung.
