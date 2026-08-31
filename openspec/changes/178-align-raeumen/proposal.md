# Change 178 — align: progress_note/pct nach skipped/done räumen

**Status:** Proposed

## Befund (2026-08-31, Live)

Nach einem `alignment=skipped` blieben `progress_note='alignment'` und
`progress_pct=1` als Restzustand am Recording stehen (Change 170 setzt
sie beim Start, der skipped-Pfad räumte sie nie). Die Chips können
dadurch einen Lauf vortäuschen, obwohl nichts läuft.

## Lösung

Im align-Worker: bei `alignment != "running"` (Endzustände skipped/done)
`progress_note` + `progress_pct` auf None setzen (vor dem Commit).

## Betroffene Dateien

- `webapp/app/service.py`
