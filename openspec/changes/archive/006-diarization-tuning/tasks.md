# Tasks — Diarization Tuning (006)

## Backend

- [x] `app/diarize.py`: `diarize()` um `num_speakers`/`min_duration_off`
      erweitern, an Pipeline durchreichen (`min_speakers/max_speakers`,
      `min_duration_off`); None → kein Kwarg (Default-Verhalten).
- [x] `app/service.py`: `_run_diarization()` + `process_recording` reichen
      die Werte vom Recording durch.
- [x] `app/models.py` + `app/crud.py`: Spalten `diarize_num_speakers`,
      `diarize_min_duration_off` (nullable).
- [x] `app/routers/recordings.py`: Form-Params bei upload/transcribe,
      JSON-Params bei retranscribe, Speicherung, `_recording_to_dict`.
- [x] `app/routers/url_import.py`: Form-Params + create_recording.
- [x] Tests: `test_diarize_params.py` (3), `test_optin_toggles.py` (2),
      Mock-Signatur `test_postprocess_pipeline.py` angepasst.
- [x] Backend-Suite grün (Diarize 15/15, betroffene 25/25).

## Frontend

- [x] `FeatureToggles.tsx`: `FeatureValues.numSpeakers`/`diarSens`,
      `diarSensToMinDurationOff()`, `<details>`-Menü hinter 🎙-Toggle.
- [x] `useLocale.ts`: 7 Keys in de/en/pt.
- [x] `RecordingCard.tsx`: Initialisierung aus Recording-Feldern
      (inkl. min_duration_off→Stufe-Rückabbildung), Durchreichung bei
      Transcribe + Re-Transcribe.
- [x] `api.ts`: `startTranscription`-Params + Form-Felder,
      `retranscribeRecording`-opts, Recording-TS-Typ.
- [x] `hooks.ts`: useRetranscribe-opts-Typ.
- [x] Tests: `diarizeParams.test.ts` (3); vitest 28/28 grün.
- [x] `npm run build` grün.

## Offen

- [ ] `openspec/`: Spec `transcription` mit MODIFIED-Delta aktualisieren
      (change 006 → specs anwenden), dann archivieren.
- [ ] Commit + Push (Backend + Frontend + openspec), CI-Watcher.
- [ ] Deploy auf whisper.example.org, Live-Test: 2-Sprecher-Aufnahme
      mit „Sprecherzahl: 2" → genau 2 Speaker; „Weniger Wechsel" → weniger
      Segment-Flicker.
