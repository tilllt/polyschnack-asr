# Change 184 — Job-Zeiten als datetime (heartbeat_at/phase_started_at)

**Status:** Proposed (Live-Befund 2026-09-03, Fix + Regressionstest folgen im Commit)

## Befund (Live 2026-09-02 20:36, prod KI-Box)

User-Symptom: Upload → transcribe → **error 500**, kein Status/Progress — die
Transkription läuft trotzdem und der Text erscheint später.

Traceback im ps-webapp-Container:

```
File "recordings.py", line 1283, in list_recordings_endpoint
    d = _recording_to_dict(r, access_level=...)
File "recordings.py", line 763, in _recording_to_dict
    "job": _job_to_dict(active_job),
File "recordings.py", line 627, in _job_to_dict
    "heartbeat_at": iso_utc(job.heartbeat_at) if getattr(job, "heartbeat_at", None) else None,
File "timeutil.py", line 22, in iso_utc
    if dt.tzinfo is None:
AttributeError: 'str' object has no attribute 'tzinfo'
```

Mechanik: Nach dem Transcribe-Start pollt die UI `GET /api/recordings` (Liste).
Jede Recording mit aktivem Job (queued/running) wird über `_job_to_dict`
serialisiert → Crash → 500 → UI zeigt „error 500" statt Jobstatus. Der
Worker-Container transkribiert unabhängig weiter → Text erscheint später.

## Root-Cause

`models.Job` deklariert zwei der vier Zeitfelder als `str`:

- `phase_started_at: Optional[str]` (models.py ~460)
- `heartbeat_at: Optional[str]` (models.py ~461)

während `started_at`/`finished_at` korrekt `Optional[dt.datetime]` sind.
`job_state.job_transition()` (Change 183) schreibt in alle vier **datetime**-
Objekte. Für die str-Felder serialisiert SQLAlchemy das datetime beim
DB-Write zu einem ISO-Text und liefert beim Read einen **str** zurück →
`iso_utc(str)` → `AttributeError`.

Warum die 183-Fixes (01.09. 03:51/03:54, b479b94 „_job_to_dict defensiv",
7b4f339 „JobRow-Import") nicht griffen: `getattr(job, "heartbeat_at", None)`
schützt nur vor *fehlenden* Attributen — `heartbeat_at` ist aber vorhanden
und nur vom falschen Typ. Der Fix deckte die Symptom-Flanke ab, nicht die
Ursache (Hotfix-Kette, Change-183-Muster). Zusätzlich deckte kein Test den
Typ nach DB-Roundtrip ab (`assert ... is not None` ist auch für str grün).

DB-Befund (03.09.): `jobs.heartbeat_at` aktuell überall NULL (Terminal-Zustand
räumt per job_transition) — der Crash tritt nur bei laufenden Jobs auf und
ist deshalb flüchtig; nach jedem Job-Start reproduzierbar.

## Fix

1. `models.py`: `phase_started_at`/`heartbeat_at` → `Optional[dt.datetime]`
   (symmetrisch zu `started_at`/`finished_at`; SQLAlchemy übernimmt den
   Roundtrip, SQLite-TEXT-Spalte bleibt physisch).
2. Regressionstest: `test_job_state.py` — nach DB-Roundtrip
   `isinstance(row.heartbeat_at, dt.datetime)` (rot vor Fix, grün danach).
3. **Datenmigration (prod):** `phase_started_at` liegt in allen 89
   `jobs`-Zeilen als ISO-Text MIT `+00:00`-Suffix vor (Befund 03.09.:
   sqlite3-String-Adapter schrieb `datetime.isoformat(sep=' ')` inkl.
   Zeitzone; SQLAlchemy-DateTime-Parser erwartet `%Y-%m-%d %H:%M:%S.%f`
   ohne Suffix → ValueError beim ersten Read nach dem Fix). Migration
   vor + nach dem Deploy (idempotent): `fromisoformat` → naive UTC →
   `strftime('%Y-%m-%d %H:%M:%S.%f')`. `started_at`/`finished_at` sind
   bereits suffixfrei (SQLAlchemy-DateTime-Bindung), `heartbeat_at` ist
   NULL (Terminal räumt) — nur `phase_started_at` ist betroffen.

Kein zusätzlicher Guard in `iso_utc` — die Invariante (datetime|None) wird
am Modell erzwungen; str-Handling würde Typfehler nur maskieren.

## Deploy

CI grün → KI-Box `./polyschnack-manage.sh pull && models && start` (Overlays!).
