# Change 028 — Bugfix: Retention-Sweep crasht bei Recordings ohne uid

## Problem

Die laufende Webapp loggt jeden Sweep-Zyklus:

```
ps-webapp-1 | retention sweep failed
ps-webapp-1 |   File "/app/app/recording_health.py", line 127, in run_health_scan
ps-webapp-1 |     names = ", ".join(b[0].uid[:8] for b in broken[:5])
ps-webapp-1 | TypeError: 'NoneType' object is not subscriptable
```

`Recording.uid` ist ein Pflichtfeld mit `default_factory=uuid4` — aber
**Legacy-Datensätze** (vor Einführung des uid-Felds, DB-Spalte nullable)
haben `uid = None`. Der Health-Scan findet solche Records als „broken"
(Datei fehlt), und das **Logging** `b[0].uid[:8]` → `None[:8]` wirft einen
TypeError.

Auswirkung: Der Sweep-Loop (`main.py::_sweep_loop`) bricht pro Zyklus ab,
nachdem `sweep`/`sweep_stale_processing` liefen — der **Health-Scan
(`run_health_scan`) kommt nie mehr zur Ausführung**, solange mindestens
ein uid-loser kaputter Datensatz existiert; Log-Spam „retention sweep
failed" pro Zyklus.

## Ziel

1. Health-Scan läuft wieder stabil (kein Crash im Logging).
2. uid-lose Legacy-Records werden weiterhin korrekt als `failed` markiert
   (das ist gewünschtes Verhalten — nur die Log-Zeile darf nicht crashen).
3. Regressionstest: `run_health_scan` mit Recording ohne uid + fehlender
   Datei → kein Exception, 1 Update.

## Was sich für Nutzer/Entwickler ändert (Verhaltens-Delta)

- Kein sichtbares Verhaltens-Delta für Nutzer; der Health-Scan markiert
  kaputte Dateien wieder wie vorgesehen (status=failed, Fehlertext).
- Log-Zeile zeigt `?` statt uid für Datensätze ohne uid.

## Abgrenzung / Ehrlichkeit

- Keine Datenmigration für uid-lose Legacy-Records in diesem Change
  (separates Thema; uid wird beim nächsten Update der Records gesetzt —
  nicht Bestandteil des Crash-Fixes). Zielablage unverändert.

## Specs-Delta

`ADDED` — `specs/engineering/spec.md`: REQ-WEB-036
