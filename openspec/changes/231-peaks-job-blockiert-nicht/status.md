# Change 231 — peaks-Job blockiert die Transkription („job failed" beim Hochladen langer Dateien)

Nutzer-Befund 21.09.2026, wörtlich:

> Beim hochladen einer langen dateiu kommt direkt ein "job failed" toast. meine vermutung, es wird direkt die transkription angeschmissen obwohl der create waveform job noch laeuft.

## Befund (belegt an der laufenden Datenbank, KI-Box)

Aufnahme 344 (`bvv01.webm`, 93,7 MB, 09:07 Uhr, Nutzer 1):

- `09:07:35.464` — Transkriptionslauf **248** angelegt → Status `failed`, **`error` = NULL**
- `09:07:35.491` — 27 ms später Job **236** `peaks-344` (kind `peaks`) gestartet, Laufzeit **29,1 s** (bis `09:08:04.590`)
- `09:09:01` — zweiter Anlauf (Lauf **249**) läuft in 23,9 s durch
- für Lauf 248 existiert **keine Job-Zeile** — der Lauf starb vor der Einreihung

Dasselbe Muster bei den Aufnahmen 342 (08:35:55) und 343 (08:37:56): peaks-Job `done`, Transkriptionslauf ohne Startzeit `failed`.

Quelle: `app/queue.py:419` — `if any(j.rec_id == rec_id for j in self._jobs.values()): raise QueueError(f"recording {rec_id} already has an active job (queued/processing)")`. Der Wächter zählte **jeden** Job der Aufnahme, also auch die Vorarbeit der Wellenform.

Zweiter Fehler: `_abort_queued_run()` (`app/routers/recordings.py`) setzte `run.status = "failed"` **ohne** Fehlertext — in der Oberfläche blieb nur „job failed" ohne Ursache (stiller Fehler).

## Umsetzung

1. `app/queue.py` — der Wächter ignoriert `peaks`-Jobs in beide Richtungen: ein peaks-Job sperrt keine Transkription, und eine laufende Transkription wird nicht durch einen peaks-Job blockiert. Begründung im Code: peaks schreibt ausschließlich Sidecar-Dateien der Wellenform und fasst `text`/`segments` nie an; der Arbeiter führt weiterhin nur einen Job gleichzeitig aus, die Transkription **wartet** jetzt hinter der Wellenform.
2. `app/routers/recordings.py` — `_abort_queued_run(..., reason=None)` schreibt den Grund in `run.error`; alle vier Aufrufer übergeben `str(exc)`.

## Offen

- Backend-Gesamtlauf nach der Änderung (läuft).
- Ausrollen zusammen mit 232/233.
