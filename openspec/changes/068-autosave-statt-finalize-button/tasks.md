# Change 068 — Tasks

## 1. Backend

- [x] `segments.py::replace_segments`: Query-Param `create_version: bool =
      True` — bei False kein snapshot (nur DB-Write); Default True
      (abwärtskompatibel)

## 2. Frontend api

- [x] `api.ts replaceSegments`: optionales `createVersion` durchreichen
      (`?create_version=false`)

## 3. useYjsTranscription

- [x] Autosave: Debounce 1500 ms auf doc-update → save(false) — atomarer
      Write ohne Version
- [x] Fingerprint-Vergleich (lastSavedRef): kein Write bei unverändertem
      Text; initial = DB-Stand (kein Erst-Write durch Doc-Befüllen)
- [x] Fehler still schlucken (nächster Retry beim nächsten Update)
- [x] Unmount-Flush: pending Änderungen mit Version sofort speichern
- [x] setEditingActive: bei aktiv→inaktiv einmalig save(true) — Version
      nur beim Edit-Mode-Ende, nur bei Änderung
- [x] enabled-Flag (Change 067-Fix): enabled=false → keine Yjs-Verbindung,
      kein WebSocket/Awareness/Solo-Timer (conn="solo")

## 4. SegmentList / RecordingCard

- [x] „In DB speichern"-Button entfernt (Kollaborations-Leiste zeigt nur
      aktive Editoren + optional „Speichert…")
- [x] collabEnabled-Prop: RecordingCard reicht `has_shares ||
      is_anon_shared || shared_with_me` durch
- [x] AnnotationThreads: kein „Noch keine Annotationen"-Hinweis mehr
      (rendert nichts bei leerer Liste)

## 5. Tests

- [x] Backend: create_version=False erzeugt keine TranscriptVersion
      (test_resegment, 2 neue Tests)
- [x] Backend: create_version=True (Default) erzeugt Version
- [x] Frontend: Mock auf save/setEditingActive/activeEditors angepasst
- [x] Frontend: AnnotationThreads-Empty-State → rendert nichts
- [x] tsc --noEmit 0 · Frontend 236/236 · Backend 13/13 (resegment+health)
- [x] npm run build ok

## 6. Abschluss

- [ ] Vollsuite fail=0 (nach Commit)
- [ ] Commit + Push + CI
