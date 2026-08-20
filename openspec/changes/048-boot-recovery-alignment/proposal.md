# Change 048: Boot-Recovery für hängende Hintergrund-Alignments

**Status:** proposal
**Datum:** 2026-08-20
**Typ:** Bugfix (Recovery)

## Problem

Change 045 (Hintergrund-Alignment) setzt nach „done" `alignment=pending`
und startet einen Hintergrund-Worker (→ `running` → `done`/`skipped`).
Wird PolySchnack währenddessen ausgeschaltet (Container-Restart,
Stromausfall), passiert:

1. Der Worker-Thread stirbt mit dem Prozess — **ohne** den Status auf
   `skipped`/`done` zu setzen.
2. Beim Boot wird **nichts** re-scheduled: Es gibt keinen Mechanismus, der
   hängende `pending`/`running`-Alignments erkennt. Der Status bleibt für
   immer `pending` — die UI zeigt einen Zustand, der nie abgeschlossen wird.
3. Verwaiste Cache-Dateien (`{DATA_DIR}/.align-cache/<rec_id>.wav` +
   `.json`) bleiben liegen (Disk-Müll, evtl. alte Audio-Daten).

Gleiches gilt für Change 046 (Re-Align-Trigger): auch dort landet ein Job
auf `pending` und stirbt mit dem Prozess.

## Lösung

**Boot-Recovery in der Lifespan** (nach `init_db()`, vor dem Start der
Background-Worker — es kann beim Boot noch keine neuen Alignments laufen):

- Alle Recordings mit `alignment IN ("pending", "running")` → `skipped`
  mit Fehlertext „Alignment nach Neustart übersprungen — Re-Align-Button
  nutzen" (der User kann das präzise Alignment jederzeit manuell nachholen).
- `.align-cache`-Dateien dieser Recordings löschen (verwaiste WIP-Artefakte).
- Log-Zeile mit Anzahl.

Warum `skipped` statt Neu-Start: Der Boot-Recovery soll deterministisch und
sofort fertig sein. Automatisches Re-Scheduling würde die Startzeit
verlängern und die Aligner-Backends direkt beim Boot belasten; der User hat
mit dem Re-Align-Button (Change 046) den kontrollierten manuellen Weg.

## Abgrenzung

- Betrifft NUR `alignment`-Feld (Hintergrund-Align), nicht den Haupt-Job
  (der Haupt-Job-Fluss wird bereits vom Stale-Processing-Watchdog geheilt:
  `processing` + keine Aktivität > 120 min → `failed`).
- Kein automatisches Löschen von Audio-Dateien (bewusst — Recording bleibt
  nutzbar, nur das Alignment-Ergebnis fehlt).
