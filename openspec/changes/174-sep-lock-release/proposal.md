# Change 174 — sep-Server: Job-Lock wird nie freigegeben

**Status:** Proposed

## Befund (2026-08-31, Live-Test)

`sep_server.py`: `_lock = threading.Lock()` (Z. 46) wird in `do_POST`
mit `acquire(blocking=False)` belegt, aber **nirgendwo released** —
`_job_finish()` setzt nur `_JOB_STATUS` zurück. Konsequenz: Nach dem
ERSTEN Job ist der Server für immer blockiert (409 „Separation läuft
bereits") bis zum Container-Neustart.

Live-Befund: Webapp-Methode A/B konnte nie erfolgreich laufen; ein
einzelner htdemucs-Job nach einem Restart blockte alle weiteren
(A/B-Tests + Webapp-Jobs → 409).

## Lösung

`_lock.release()` in `_job_finish()` (defensiv gegen Doppel-Release).
Zusammen mit Change 172 (GPU-Overlay) läuft die Separation erstmals
durchgängig.

## Betroffene Dateien

- `sep-service/sep_server.py`
