# Change 067 — DB-Erreichbarkeit sichtbar machen: Health-Check + klare Fehler

**Status:** in Arbeit · **Datum:** 2026-08-21

## Problem

Produktionsvorfall (2026-08-21): Die DB war nicht erreichbar (SQLite
nicht verfügbar — QueuePool-Timeout/Lock/Volume), aber die Webapp meldete
das **still**: `/api/stats` lieferte `total: 0`, die Recordings-Liste `[]`,
Sortieren/Filtern nach Tags ließ die Seite hängen/„tot" wirken. Erst der
Blick ins Log zeigte `QueuePool limit of size 5 overflow 10`. **Stille
Fehler sind inakzeptabel** (User-Prinzip): Die Webapp muss DB-Probleme
selbst erkennen und sichtbar melden.

## Ziel

1. **`/health` prüft die DB**: zusätzlich zu `status: ok` ein `db`-Feld
   (`ok` oder `error: <kurz>`); der Healthcheck führt `SELECT 1` mit kurzem
   Timeout aus. Liveness bleibt 200 (Container wird nicht gekillt), aber der
   DB-Status ist sofort sichtbar (Docker-Healthcheck-Log, curl, Monitoring).
2. **DB-Fehler in Daten-Routen sind sichtbar**: `GET /api/stats`,
   `GET /api/recordings` (und die Listen-Filter) werfen bei
   DB-Connection-Fehlern **503 mit klarer Meldung** („Datenbank nicht
   erreichbar — bitte Stack/Volume prüfen") statt stille Nullwerte/leere
   Listen zu liefern. Frontend zeigt den Fehler (Toast/Fehlertext), nicht
   eine leere Seite.
3. Kein neues Verhalten bei gesunder DB (Identität der Antworten).

## Verhaltens-Delta (IST → SOLL)

- **IST:** `/health` = reine Liveness ohne DB-Kenntnis; DB-Fehler in
  Stats/Listen → 500 (Server-Trace) oder stille leere Ergebnisse.
- **SOLL:** `/health` meldet `db: ok|error`; Stats/Listen-Fehler →
  **503 + `{"detail": "Datenbank nicht erreichbar …"}`**; Frontend zeigt
  Fehler sichtbar (i18n de/en/pt).

## Umsetzung (Skizze)

1. `db.py`: `db_health() -> tuple[bool, str]` — `SELECT 1` mit
   `execution_options(timeout=…)`/kurzem Versuch, Exception → (False, msg).
2. `main.py /health`: `{"status": "ok", "db": db_health(), "asr_url": …}`.
3. `crud.py get_stats` + `routers/recordings.py` (Liste/Filters):
   try/except um die Session-Queries → `HTTPException(503, …)` mit
   deutscher Meldung; Log mit Ursache.
4. Frontend: `api.ts`/Liste — bei 503 Fehlermeldung statt leerer Render.
5. Tests: Health-Response enthält db-Feld; Stats-503 bei kaputter Engine
   (Monkeypatch); Frontend-Fehlerpfad.

## Referenzen

- Vorfall: ps-webapp-1 Log, `QueuePool limit of size 5 overflow 10`
  (2026-08-21); `/api/stats` → total 0 bei nicht erreichbarer DB
- Change 066: NullPool-Fix (behebt die Pool-Erschöpfung als Ursache) —
  067 macht den Zustand sichtbar
