# Change 189 — Speichern mit Versionsprüfung (kein stilles Überschreiben)

## Warum

Die App speichert Segmente **client-autoritativ**: Der Browser schickt beim
Speichern die **komplette** Segmentliste (Text + Wörter + Grenzen) und der
Server schreibt sie unverändert über den Bestand — ohne jede Prüfung, was
inzwischen serverseitig passiert ist. Zusätzlich legt der Yjs-Raum pro
Aufnahme eine Textkopie über die geladenen Daten.

Folgen (belegt am 14.09.2026, Aufnahme 328):

1. Ein serverseitiger Reparaturschreibvorgang (fehlender Passus eingesetzt,
   17:34, Version 11) wurde um **17:44** von einem offenen Browserfenster
   mit dessen geladenem Stand überschrieben (Versionen 14/15: Text ohne
   Passus, alte Segmentgrenzen). Der Nutzer sah seine Änderung „zurückfallen".
2. Der Nutzer konnte nicht erkennen, *warum* — es gab keine Fehlermeldung,
   keinen Konflikt, keinen Hinweis. Stiller Datenverlust, genau die Klasse,
   die wir nicht akzeptieren.

## Was sich ändert

- **Optimistische Sperre:** Der volle Listen-PUT
  (`PUT /api/recordings/{rid}/segments`) nimmt `expected_updated_at` mit —
  den Stand, den der Client geladen hat. Passt er nicht zum aktuellen
  `updated_at`, antwortet der Server **409 `stale_write`** mit dem aktuellen
  Zeitstempel und ändert **nichts**.
- **Frontend:** 409 wird sichtbar gemeldet („Aufnahme wurde zwischenzeitlich
  geändert — bitte neu laden"), mit Knopf zum Neuladen; der lokale Stand wird
  **nicht** blind erneut geschrieben.
- **Yjs-Raum folgt dem Serverstand:** Ein Raum wird an `updated_at` gebunden;
  hat sich der Serverstand seit dem Raum-Start geändert, wird der Raum neu
  befüllt, statt alten Text über neue Daten zu legen.
- **Betriebsregel in der Doku:** Serverseitige Reparaturen nur bei
  geschlossener Sitzung bzw. nach Raum-Reset.

## Auswirkung

Rückwärtskompatibel: Ohne `expected_updated_at` verhält sich der Endpunkt wie
bisher (Skripte, Tests) — aber er protokolliert „PUT ohne Versionsprüfung" mit
`rec_id`, damit solche Schreibvorgänge auffindbar sind. Die UI sendet das Feld
immer.
