## MODIFIED Requirements

### Requirement: Text-Edit (Erzwungener Sync)

- **Ergänzung (Change 143):** Die lokale Anzeige-Wahrheit
  (`localPendingRef`/`localTexts`) wird erst nach der Server-Bestätigung
  (PUT-Erfolg) freigegeben. Ein paralleler Detail-Poll (2-s-Intervall)
  mit einer VOR dem PUT-Commit aufgenommenen Antwort kann den Cache zwar
  überschreiben, aber nie die Anzeige zurückkippen lassen.

#### Scenario: Poller-Race nach Edit-Ende

- Given: Detail-Poller aktiv (status done, 2-s-Intervall) und der User
  editiert einen Segment-Text
- When: Der User verlässt den Edit-Mode (Save) und der Poller liefert
  zwischenzeitlich eine Antwort vom Stand VOR dem PUT-Commit
- Then: Die Anzeige bleibt auf dem Edit-Stand; nach der
  Server-Bestätigung zeigt sie den gespeicherten Stand; ein erneuter
  Edit-Einstieg zeigt denselben Stand wie die Anzeige

### Requirement: Queue (zuverlässige Job-Verarbeitung)

- **Ergänzung (Change 143):** Nach einem Webapp-Neustart werden DB-Jobs
  mit status='queued' beim Start wieder in die Verarbeitung aufgenommen
  (keine verwaisten Jobs). Scheitert das Enqueue nach dem Run-Commit,
  wird der Run auf 'failed' gesetzt (kein Orphan 'queued').

#### Scenario: Neustart mit queued-Job

- Given: Ein Run wurde enqueued, aber der Webapp-Prozess startet neu,
  bevor der Worker ihn verarbeitet
- When: Die Webapp startet
- Then: Der Job wird wieder in die Queue aufgenommen und verarbeitet
