# Change 054 — Tasks

## Phase 1: Backend (Modell, Migration, Sortierung, Filter, Tags)
- [x] `models.py`: `tags: List[str] = Field(default_factory=list, sa_column=Column(JSON))`
      am `Recording` (+ Kommentar Change 054)
- [x] Migration: Auto-ALTER beim Start — fehlende `tags`-Spalte per
      `PRAGMA table_info` erkennen und `ALTER TABLE recordings ADD COLUMN tags JSON`
      ausführen (bestehendes Muster; Ort: db-Init/Startup neben bestehenden
      ALTERs, falls vorhanden, sonst neuer kleiner Helfer in `db.py`)
- [x] `crud.list_recordings`: Parameter `sort: str = "date"`, `dir: str = "desc"`,
      `tags: list[str] | None` — Mapping:
      `date → created_at`, `edited → updated_at`, `name → title` (Fallback
      original_name; SQL: `func.coalesce(title, original_name)`),
      `filename → original_name`, `length → duration_s`; NULLs (duration)
      ans Ende; Tag-Filter als ODER (Recording gehört zum Filter, wenn
      mindestens eines der angefragten Tags gesetzt ist); Default-Verhalten
      unverändert (`date desc`)
- [x] `routers/recordings.py`: `GET /api/recordings` um `sort`, `dir`, `tag`
      (mehrfach) erweitern; `_recording_to_dict` um `tags` ergänzen
- [x] Neue Route `PATCH /api/recordings/{uid}/tags` (Body `{"tags": [...]}`,
      write-Zugriff via `ensure_access`, dedup + trim, max. 20 Tags,
      Tag-Länge ≤ 40 Zeichen, leere Einträge verworfen) → gibt neue Tags zurück
- [x] `updated_at` bei Segment-Änderungen setzen: `PUT …/segments`
      (`segments.py`), `PATCH …/segments/{sid}` und Titel-Edit-Route
      (prüfen, ob dort schon gesetzt) → `rec.updated_at = now`
- [x] Backend-Tests: Sortierung je Kriterium + Richtung, NULL-Duration ans
      Ende, Tag-Filter (ODER, kombiniert mit q), PATCH tags (Auth write,
      dedup/trim/Limits), updated_at nach Segment-PUT

## Phase 2: Frontend (Sort-Badges, Filter, Tag-Editor)
- [x] `api.ts`: `Recording`-Typ um `tags: string[]` ergänzen; `fetchRecordings`
      um `sort`/`dir`/`tag`-Parameter; neue `updateRecordingTags(uid, tags)`
- [x] Neue Komponente `SortBadges` (oder in RecordingList): fünf Badges
      (Date, Last edit, Name, Filename, Length), Klick-Zyklus desc → asc →
      Default (3. Klick deaktiviert), aktives Badge mit ↑/↓-Marker,
      i18n-Strings de/en
- [x] Tag-Filter-Leiste: aus den geladenen Recordings aggregierte Tags
      (nur ≥ 1 Vorkommen) als Chips mit Count; Klick toggelt Filter;
      Kombination mit Suche q; aktive Chips hervorgehoben
- [x] `RecordingCard`: Tag-Anzeige + Editor (Chips mit ×, Eingabefeld +
      Enter zum Hinzufügen, persistiert via `updateRecordingTags`; Fehler
      sichtbar, kein stiller Fail)
- [x] Sortierung/Filter in `App.tsx` verdrahten (State `sort`/`dir`/`activeTags`,
      an Fetch und RecordingList durchreichen)
- [x] Frontend-Tests: Badge-Zyklus (desc → asc → default), Tag-Filter-
      Aggregation (nur Tags ≥ 1, Counts), Tag-Editor (add/remove → API-Call),
      Sortier-Reihenfolge der gerenderten Cards

## Phase 3: Qualität
- [x] `tsc --noEmit` sauber, vitest vollständig grün, Backend-Suite grün
- [x] OpenSpec-Proposal auf Ist-Stand abgleichen („Umgesetzt"-Marker in tasks)
- [ ] Commit + Push; CI-Pipelines (test-frontend, test-webapp) prüfen und melden
