# Spezifikation — transcription-view (Change 189)

## ADDED Requirements

### Requirement: Req 189-1 — Speichern prüft den geladenen Stand

Der volle Listen-PUT (`PUT /api/recordings/{rid}/segments`) MUSS den vom
Client zuletzt geladenen `updated_at`-Wert (`expected_updated_at`) entgegennehmen
und gegen den aktuellen Stand der Aufnahme prüfen.

#### Scenario: Zwischenzeitliche Änderung wird erkannt

- **GIVEN** ein Client, der die Aufnahme mit `updated_at = T1` geladen hat
- **AND** eine serverseitige Änderung, die `updated_at = T2` gesetzt hat (T2 > T1)
- **WHEN** der Client die Segmentliste mit `expected_updated_at = T1` speichert
- **THEN** antwortet der Server **409** mit `current_updated_at = T2`
- **AND** die gespeicherten Segmente, der Text und die Versionsliste bleiben
  unverändert (keine neue Version)

#### Scenario: Aktueller Stand wird gespeichert

- **GIVEN** ein Client, der die Aufnahme mit `updated_at = T2` geladen hat
- **AND** keine zwischenzeitliche Änderung
- **WHEN** der Client mit `expected_updated_at = T2` speichert
- **THEN** wird gespeichert, eine Version angelegt und `updated_at` erneuert

#### Scenario: Ohne Feld bleibt der Endpunkt nutzbar

- **WHEN** ein Aufruf `expected_updated_at` nicht mitschickt
- **THEN** verhält sich der Endpunkt wie bisher
- **AND** der Server protokolliert den Schreibvorgang als „ohne Versionsprüfung"

### Requirement: Req 189-2 — Konflikt wird sichtbar, nicht still

Das Frontend MUSS einen 409 sichtbar anzeigen und den lokalen Stand NICHT
automatisch erneut senden.

#### Scenario: Konflikt beim Speichern

- **GIVEN** ein offener Edit-Modus
- **WHEN** das Speichern mit **409** antwortet
- **THEN** erscheint ein Hinweis „Aufnahme wurde zwischenzeitlich geändert —
  bitte neu laden" mit einer Aktion zum Neuladen
- **AND** es findet kein automatischer Wiederholungsversuch statt

### Requirement: Req 189-3 — Kollaborationsraum folgt dem Serverstand

Der Yjs-Raum einer Aufnahme MUSS an ihren `updated_at`-Stand gebunden sein.

#### Scenario: Alter Raumtext überlagert keine neuen Daten

- **GIVEN** ein offener Raum zu Stand T1
- **AND** ein serverseitig geänderter Stand T2
- **WHEN** ein Client mit Stand T2 den Raum betritt
- **THEN** erhält er einen Raum mit leerem/aktuellem Stand und befüllt ihn aus
  dem Serverstand
- **AND** der Text aus T1 wird nicht angezeigt
