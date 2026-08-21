# Change 059 — Schnelle Liste im langsamen Netz: lite-Payload + Nachladen von Transkription/Waveform

## Problem

`GET /api/recordings` serialisiert für JEDE Aufnahme den kompletten Datensatz
(`_recording_to_dict`, recordings.py:503) — inklusive **`text`, `segments`
(mit Word-Timestamps + Confidence) und `waveform_peaks`**. Bei vielen
Aufnahmen und langsamen Verbindungen ist das die dominierende Latenz: Die
Karten-Metadaten (Titel, Status, Dauer, Badges) können nicht gerendert
werden, bevor die ganzen Transkriptionen übertragen sind. User-Befund:
„können wir das GUI so umstrukturieren, dass sie auch bei langsamem Netz
schneller geändert wird und nur die datenintensiven Teile (Waveform,
Transkription) mit einem 'Loading…'-Hinweis nachladen?"

## Ziel

1. **Shell-first:** Die Aufnahmen-Liste liefert nur Metadaten (Karten-Shell)
   — `text`, `segments`, `waveform_peaks` entfallen im Listen-Payload
   (`lite`-Modus). Die Liste rendert sofort.
2. **Nachladen pro Karte:** Beim Aufklappen einer Karte (done/processing)
   lädt `GET /api/recordings/{rid}` (existiert bereits) Transkription +
   Peaks nach — mit sichtbarem „Loading…"-Hinweis an der Transkript-Stelle
   und dem bestehenden Waveform-Platzhalter.
3. **Kein Doppel-Fetch, keine Staleness:** react-query-Cache pro `uid`
   (`["recording-detail", uid]`); Polling alle 2 s NUR während
   `processing` (Live-Streaming bleibt live); nach Status-Wechsel auf
   `done` ein finaler Refetch. Edits (handleEdited) schreiben segments/text
   zusätzlich in den Detail-Cache (Single Source of Truth bleibt das Modell).
4. **Kollabierte Karten laden gar nichts** (Transkription wie bisher).

## Umsetzung

### Backend (`webapp/app/routers/recordings.py`)

- `_recording_to_dict(rec, access_level, lite=False)`: bei `lite=True` →
  `"text": None`, `"segments": None`, `"waveform_peaks": None`; alle
  Metadaten (uid, title, tags, status, duration_s, size_bytes, language,
  progress_*, URLs, toggles, shared_with_me, …) bleiben.
- `list_recordings_endpoint(..., lite: bool = Query(False))` → an
  `_recording_to_dict` durchreichen. Default `False` = bestehendes Verhalten
  (Backend-Tests unverändert), Frontend fordert `lite=1` explizit an.
- Peaks-Nachzug (`_schedule_peaks`, Backfill) bleibt unverändert.

### Frontend

| Datei | Änderung |
|---|---|
| `api.ts` | `fetchRecordings(..., lite=true)`: `lite=1`-Param anhängen. `Recording.text: string \| null` |
| `hooks.ts` | `useRecordingDetail(uid, enabled)` — QueryKey `["recording-detail", uid]`, `enabled` nur bei aufgeklappter Karte (done/processing), `refetchInterval` 2 s bei `processing` |
| `RecordingCard.tsx` | `segments = detail?.segments ?? r.segments`, `recText = detail?.text ?? r.text`; `peaks={detail?.waveform_peaks ?? r.waveform_peaks}`; Loading-Placeholder `loading_transcript` (Skeleton) solange Detail lädt und noch nichts da ist; `handleEdited` aktualisiert auch den Detail-Cache; Refetch-Effekt wenn Listen-Status `done` aber Detail veraltet |
| `useLocale.ts` | Key `loading_transcript` (de/en/pt) |

## Tests

- Backend (`tests/`): `lite=1` → `text`/`segments`/`waveform_peaks` sind
  `null`, Metadaten + URLs vorhanden; ohne `lite` → alles wie bisher.
- Frontend (`RecordingCard.test.tsx`): Mock um `useRecordingDetail`
  erweitern (bestehende Tests bleiben grün); neuer Test: aufgeklappte Karte
  löst Detail-Fetch aus; Loading-Hinweis sichtbar, solange das Detail
  pending ist.
- `npm test` + `npm run build` grün; Backend-Suite (`run_full_suite.sh`).

## Out of Scope

- Serverseitige Pagination/Virtualisierung der Liste (folgt separat, wenn
  nötig).
- `SharedRecordingView` (`/r/:uid`) nutzt bereits `fetchRecording` (voll).
- Backend-Sortierung/Suche (`q`) unverändert (SQL-seitig, braucht kein
  Payload-Text).
