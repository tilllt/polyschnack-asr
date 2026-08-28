# Change 143: Edit-Sync (Poller-Race) + Queue-Recovery + Process-Button

**Status:** Archived

## Problem (User-Befunde 2026-08-28)

1. **Edit-Sync weiterhin defekt:** Edit-Mode → ändern → verlassen → alter
   Text; erneut in den Edit-Mode → Änderung wieder da. Change 139 (synchroner
   onEdited + PUT) hat das Symptom nicht behoben.
2. **Re-Transcribe hängt:** Job wird „zur Queue hinzugefügt", startet aber
   nie.
3. **Start-Button** wird mit dem Play-Button verwechselt → umbenennen in
   „Process".

## Ursachen (analysiert)

1. **Poller-Race (Edit-Sync):** Der Detail-Poller (2-s-Interval, Change 138)
   holt während des laufenden PUTs den ALTEN Server-Stand und überschreibt
   damit den optimistischen Cache (handleEdited). Der SegmentList-Guard
   (`localPendingRef`) fiel bereits beim optimistischen Sync (propFp ===
   localFp) — die Anzeige kippte nach dem Edit-Ende zurück.
2. **Verwaiste queued-Jobs:** Nach einem Webapp-Neustart kennt der
   In-Memory-QueueManager DB-Jobs mit status='queued' nicht mehr → kein
   Worker startet sie. Zusätzlich: Wird der Run committet, BEVOR enqueue()
   läuft, und enqueue wirft (QueueError/QueueFullError), bleibt ein
   Orphan-Run als 'queued' in der DB.

## Lösung

1. `localPendingRef` bleibt bis zur Server-Bestätigung (PUT-Erfolg) gesetzt;
   `handleSave` gibt die Anzeige erst NACH der Server-Antwort frei. Der
   Poller kann den Cache zwar überschreiben, die Anzeige bleibt aber auf dem
   lokalen Edit-Stand (ehrlich), und nach dem PUT-Erfolg liefert der Poller
   nur noch den neuen Stand.
2. `QueueManager._recover_queued()`: Beim Start werden DB-Jobs mit
   status='queued' wieder in den Manager geladen (FIFO hinten, Cancel-Guard
   verhindert Doppelstart). `_abort_queued_run()`: Bei enqueue-Fehlern wird
   der committete Run auf 'failed' gesetzt und der Run-Zeiger zurückgerollt.
3. `start_btn` → „Process" (alle Locales).
