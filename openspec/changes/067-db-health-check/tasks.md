# Change 067 — Tasks

## 1. Backend DB-Check

- [x] `db.py`: `db_health() -> tuple[bool, str]` — SELECT 1, Exception →
      (False, msg[:160])
- [x] `main.py /health`: `{"status": "ok", "db": {"ok": bool, "error": str},
      "asr_url": …}` — Liveness bleibt 200

## 2. Sichtbare DB-Fehler in Daten-Routen

- [x] Globaler Exception-Handler auf `SQLAlchemyError` (main.py) → **503**
      mit „Datenbank nicht erreichbar — bitte Stack/Volume prüfen." —
      deckt auch Dependency-Fehler (`Depends(get_session)`) ab; Log mit
      Ursache (log.error)
- [x] Kein Catch-all: nur SQLAlchemyError registriert, Rest = Default

## 3. Frontend

- [x] Kein Change nötig: `checkOk` reicht 503-detail durch,
      `App.tsx` zeigt `isError` + Message bereits (error_loading)

## 4. Tests

- [x] `tests/test_db_health.py` (3): health db ok; recordings-503;
      stats-503 — grün
- [ ] Vollsuite fail=0 (nach Commit; 065/066-Suite lief grün bis auf
      test_models_matrix — in 31f67b0 gefixt)

## 5. Abschluss

- [ ] Commit + Push + CI
