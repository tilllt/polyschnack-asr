# Change 066 — DB-Pool-Fix: QueuePool-Timeout auf SQLite (Produktionsfehler)

**Status:** in Arbeit · **Datum:** 2026-08-21

## Problem

Produktionsfehler auf der Box (`ps-webapp-1`):

```
sqlalchemy.exc.TimeoutError: QueuePool limit of size 5 overflow 10 reached,
connection timed out, timeout 30.00
```

Der Stacktrace zeigt einen **normalen, kurzen Request** (`require_authenticated`
→ `session.get(User, …)`), der 30 s auf eine freie DB-Connection wartet —
alle 15 QueuePool-Slots (5 Pool + 10 Overflow, SQLAlchemy-Default) waren
belegt.

**Ursache:** `db.py` erzeugt die Engine ohne Pool-Konfiguration
(`create_engine("sqlite:///…", connect_args={"check_same_thread": False})`)
→ SQLAlchemy-Default = **QueuePool(5 + 10)**. Für SQLite (Datei-basiert,
WAL) ist ein Connection-Pool mit künstlicher Obergrenze der falsche Ansatz:
Connections sind billig (Datei-Handle), und bei der Lastverteilung der App —
61 Routen mit `Depends(get_session)`, parallele Worker-Threads
(`run_sync_in_worker_thread`), Yjs-WebSocket-Räume, langlaufende
Uploads/Transkriptionen mit offener Session — ist die 15er-Grenze schnell
erschöpft; neue Requests verhungern mit 30-s-Timeout.

Kein Connection-Leak gefunden (alle Sessions in `with Session(engine)` oder
Generator-Dependency, sauber geschlossen).

## Ziel

1. **Keine künstliche Pool-Grenze**: SQLite-Engine mit `poolclass=NullPool` —
   jede Session bekommt eine frische Connection, die beim Schließen sofort
   freigegeben wird. Kein Pool-Timeout mehr möglich (SQLite + WAL erlaubt
   viele parallele Verbindungen; `busy_timeout=30000` bleibt als
   Schreib-Kollisions-Schutz).
2. Verhalten unverändert: Session-Semantik (Commit/Rollback durch Aufrufer),
   WAL-Pragmas, Auto-Migration.

## Verhaltens-Delta (IST → SOLL)

- **IST:** Bei > 15 gleichzeitig offenen Session-Connections bekommen neue
  Requests nach 30 s `TimeoutError` → 500 für den Nutzer.
- **SOLL:** Keine Verbindungs-Obergrenze (NullPool); Requests brauchen nie
  auf eine freie Pool-Slot zu warten. SQLite serialisiert Schreibzugriffe
  ohnehin (WAL + busy_timeout); Leser laufen parallel.

## Umsetzung (Skizze)

1. `db.py`: `poolclass=NullPool` in `create_engine` (Import aus
   sqlalchemy.pool).
2. Tests: bestehende Suite (Vollsuite) — DB-Verhalten unverändert.
3. Deploy-Hinweis in docs (env.md/README): kein Config-Eingriff nötig,
   wirkt mit nächstem Image.

## Referenzen

- Stacktrace: ps-webapp-1, `QueuePool limit of size 5 overflow 10`,
  `run_sync_in_worker_thread` → `require_authenticated` (2026-08-21)
- SQLAlchemy-Doku: QueuePool für Datei-DBs ungeeignet (SQLite-Connections
  sind billig; NullPool ist der Standard für Web-Apps mit SQLite)
