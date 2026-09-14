# Spezifikation — transcription-view (Change 190)

## ADDED Requirements

### Requirement: Req 190-1 — Gespeicherte Wörter haben eine Mindestdauer

Jedes gespeicherte Wort MUSS eine Dauer von mindestens 80 ms haben.

#### Scenario: Null-Dauer wird angehoben

- **GIVEN** ein Wort mit `end == start`
- **WHEN** die Wortliste normalisiert wird
- **THEN** gilt `end - start >= 0.08`
- **AND** der Start des Wortes bleibt unverändert

#### Scenario: Folgewort am gleichen Start

- **GIVEN** zwei Wörter mit identischem `start`
- **WHEN** normalisiert wird
- **THEN** haben beide mindestens 80 ms Dauer
- **AND** das zweite Wort beginnt nicht vor dem Ende des ersten
  (Kaskade statt Überlappung)

#### Scenario: Echte längere Dauer bleibt unangetastet

- **GIVEN** ein Wort mit `end - start = 0.42`
- **WHEN** normalisiert wird
- **THEN** bleiben `start` und `end` unverändert
