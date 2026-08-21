# Tasks — Change 059 (Lite-Liste + Nachladen)

## Backend

- [ ] `_recording_to_dict(rec, access_level=None, lite=False)`: `lite=True` → `text`/`segments`/`waveform_peaks` = `None`.
- [ ] `list_recordings_endpoint`: Query-Param `lite: bool = False`, durchreichen.
- [ ] Test (Backend): `lite=1` → 3 Felder null, Metadaten/URLs da; ohne lite → unverändert voll.

## Frontend API/Hooks

- [ ] `api.ts fetchRecordings`: `lite`-Param (Default true) → `lite=1` im Query.
- [ ] `api.ts`: `Recording.text` nullable (`string | null`).
- [ ] `hooks.ts`: `useRecordingDetail(uid, enabled)` mit QueryKey `["recording-detail", uid]`, Polling 2 s bei `processing`.

## RecordingCard

- [ ] `segments`/`recText`/`peaks` aus Detail (Fallback auf `r.*`).
- [ ] Loading-Placeholder `loading_transcript` (Skeleton) solange Detail lädt und keine Segmente da sind.
- [ ] `handleEdited` schreibt zusätzlich in den Detail-Cache.
- [ ] Refetch-Effekt: Listen-Status `done` + Detail veraltet → refetch.

## i18n + Tests

- [ ] `loading_transcript` de/en/pt.
- [ ] Frontend-Test: aufgeklappte Karte fetcht Detail; Loading-Hinweis bei pending Detail.
- [ ] `npm test` + `npm run build` grün; Backend-Suite grün.
- [ ] Commit + Push main, CI-Check.
