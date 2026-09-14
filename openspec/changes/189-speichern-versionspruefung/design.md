# Design — Change 189

## Vertrag

`PUT /api/recordings/{rid}/segments`

```
{ "expected_updated_at": "2026-09-14T17:49:34.626258Z", "segments": [ … ] }
```

- Feld vorhanden und **unpassend** → `409 {"detail": "stale_write",
  "current_updated_at": "…", "expected_updated_at": "…"}`, **kein** Write,
  **keine** Version.
- Feld vorhanden und passend → normales Verhalten (Write + Version).
- Feld fehlt → bisheriges Verhalten, aber `log.warning("PUT ohne
  Versionsprüfung rec_id=%s")`.

Der Vergleich läuft auf dem **auf Sekundenbruchteile identischen** Wert, den
der Client aus `GET /api/recordings/{rid}` bekommen hat (`updated_at` wird als
ISO-8601 mit UTC übergeben). Verglichen wird tolerant: gleicher Zeitstempel
bis auf 1 ms.

## Warum Zeitstempel und keine Revisionsnummer

`updated_at` existiert bereits, wird bei jedem Write gesetzt (Change 054) und
steht in jeder Antwort — es braucht keine neue Spalte, keine Migration und
wirkt auch für Schreibvorgänge außerhalb des UI (Migration, Reparatur,
Import).

## Yjs-Raum an den Serverstand binden

Der Raum (heute `room = uid`) bekommt einen Suffix aus dem `updated_at`-Stand
(`uid:<epoch_ms>`), mit dem der Client den Raum betritt. Ein Client mit altem
Stand landet in einem **neuen, leeren** Raum und befüllt ihn aus dem
Serverstand — alter Text kann nicht mehr über neuen gelegt werden. Räume ohne
Verbindung werden wie bisher aufgeräumt (`auto_clean_rooms`).

## Frontend

- Beim Laden merkt sich der Client `updated_at` (`loadedAtRef`).
- Jeder volle Listen-PUT schickt `expected_updated_at`.
- 409 → Banner „Zwischenzeitlich geändert" + „Neu laden"-Knopf; der lokale
  Edit-Puffer bleibt sichtbar, wird aber nicht automatisch erneut gesendet
  (kein Retry-Sturm).
- Nach erfolgreichem Write wird `updated_at` aus der Antwort übernommen.

## Teststrategie

- Backend: PUT mit passendem/falschem/fehlendem `expected_updated_at`;
  Prüfen, dass bei 409 **keine** neue Version entsteht und der Text unverändert
  bleibt (Kern der Regression).
- Frontend: `replaceSegments` sendet das Feld; 409 setzt den Banner-State.
- Regressionstest aus dem Vorfall: zwei Clients simulieren — A lädt, B schreibt
  serverseitig, A speichert → 409, Serverstand bleibt Bs Stand.
