# Spezifikation — transcription-view (Change 192)

## ADDED Requirements

### Requirement: Req 192-1 — Kopfzeile in einer Zeile, Nutzerbereich rechtsbündig

Die Kopfzeile MUSS Logo, Menü und Sprachwahl in einer Zeile führen; Guthaben,
Username und das An-/Abmelde-Symbol stehen rechtsbündig in derselben Zeile.

#### Scenario: Anordnung

- **GIVEN** ein angemeldeter Nutzer
- **WHEN** die Seite lädt
- **THEN** stehen Guthaben, Name und Symbol rechts in der Logo-Zeile
- **AND** die Sprachwahl steht rechts neben dem Menü, nicht am Zeilenende

### Requirement: Req 192-2 — Sprachwähler als Flaggen-Dropdown

Die Sprachwahl MUSS als Dropdown mit Landesflaggen umgesetzt sein und sich per
Klick außerhalb sowie Escape schließen.

#### Scenario: Auswahl einer Sprache

- **WHEN** das Flaggen-Dropdown geöffnet und „🇬🇧 English" gewählt wird
- **THEN** ist Englisch aktiv und das Dropdown geschlossen

#### Scenario: Schließen ohne Auswahl

- **WHEN** das Dropdown geöffnet ist und Escape gedrückt wird
- **THEN** schließt es, ohne die Sprache zu ändern

### Requirement: Req 192-3 — Status auf drei Kennzahlen

Die Statuszeile MUSS genau die Anzahl der Aufnahmen, die Gesamtlänge und den
Speicherbedarf zeigen.

#### Scenario: Kennzahlen

- **WHEN** die Statuszeile gerendert wird
- **THEN** sind Aufnahmen, Gesamtlänge und Speicher sichtbar
- **AND** die Zähler „fertig", „hochgeladen" und „in Arbeit" fehlen
