# Change Proposal 006 — Diarization Tuning

**Status:** Archived (auf `specs/transcription/spec.md` angewendet, 2026-08-02)

## Why

- Die Diarization (pyannote) lief bisher mit Pipeline-Defaults: unbekannte
  Sprecherzahl und aggressive Sprecherwechsel. Ergebnis: „Speaker 3 statt 2",
  Flickering bei realen Aufnahmen. User kann das nicht beeinflussen.

## What (Verhaltens-Delta)

- **Sprecheranzahl wählbar:** An der Transcribe-Zeile kann der User die
  bekannte Sprecherzahl angeben (Auto / 1 / 2 / 3 / 4+). Vorher: immer Auto.
  → Verhalten: Bei „2" erhält die pyannote-Pipeline `min_speakers=max_speakers=2`
  statt freier Schätzung. Das behebt „Speaker 3 statt 2" bei 2-Sprecher-Aufnahmen.
- **Sensitivität wählbar:** Der User wählt „Weniger Wechsel / Standard / Mehr
  Detail". Vorher: immer Standard (Pipeline-Default `min_duration_off≈0.1 s`).
  → Verhalten: „Weniger Wechsel" setzt `min_duration_off=0.4 s` (unterdrückt
  Label-Flickering), „Mehr Detail" 0.05 s. „Standard" lässt den Default stehen.
- **Beide Werte bleiben am Recording hängen:** Werden bei Transcribe und
  Re-Transcribe gespeichert und beim erneuten Transkribieren wieder verwendet
  (und im UI vorbelegt). Vorher: keine Speicherung.
- **API:** `POST /recordings/{id}/transcribe`, `…/retranscribe`,
  `POST /recordings` (Upload) und `POST /recordings/from-url` akzeptieren
  zusätzlich `diarize_num_speakers` (int, optional) und
  `diarize_min_duration_off` (float, optional). Ohne Angabe: unverändertes
  Verhalten (None → Pipeline-Default).
- **Backend-Kette:** `service.py::process_recording` reicht beide Werte an
  `diarize.py::diarize(audio_path, num_speakers=…, min_duration_off=…)`, das
  sie als `min_speakers/max_speakers` bzw. `min_duration_off` an die
  pyannote-Pipeline übergibt.

## Changes

- `app/diarize.py` — `diarize()` bekommt `num_speakers`/`min_duration_off`.
- `app/service.py` — `_run_diarization()` + `process_recording` reichen durch.
- `app/models.py`, `app/crud.py` — neue Recording-Spalten
  `diarize_num_speakers`, `diarize_min_duration_off`.
- `app/routers/recordings.py`, `app/routers/url_import.py` — neue
  Form/JSON-Params, Speicherung, Response-Felder.
- Frontend: `FeatureToggles.tsx` (ausklappbares Menü „Sprecher-Einstellungen"),
  `RecordingCard.tsx`, `api.ts`, `hooks.ts`, `useLocale.ts` (de/en/pt).

## Specs-Delta

- **MODIFIED** `specs/transcription/spec.md` → Req 2 (Transkribieren &
  Retranskribieren): zusätzliche Eingaben `diarize_num_speakers` /
  `diarize_min_duration_off`, Speicherung am Recording, Durchreichung an die
  pyannote-Pipeline, UI-Menü „Sprecherzahl"/„Sensitivität"; zwei neue
  Scenarios („Bekannte Sprecherzahl vorgeben", „Weniger Sprecherwechsel").
  Vollständiger SOLL-Stand: `changes/006-diarization-tuning/specs/transcription/spec.md`.
- Keine ADDED/DELETED/RENAMED-Specs.

## Tests

- `test_diarize_params.py` (3): Durchreichung an Pipeline, Default-Verhalten.
- `test_optin_toggles.py` (2): Speicherung am Recording, Default None.
- `diarizeParams.test.ts` (3): Sensitivitäts→min_duration_off-Mapping.

## Downgrade

- Tuning-Parameter entfernen → Diarization läuft wieder mit Pipeline-Defaults
  (Spalten bleiben, werden aber nie gesetzt und sind null).
