# Spezifikation — transcription-view (Change 191)

## ADDED Requirements

### Requirement: Req 191-1 — Top-Menü mit vier Ansichten

Die Kopfzeile MUSS ein Menü mit den Einträgen „Transkribieren" (Default),
„Settings", „Benchmark" und „Admin" anbieten und den aktiven Eintrag sichtbar
hervorheben.

#### Scenario: Default ist Transkribieren

- **GIVEN** ein angemeldeter Nutzer auf der Startseite
- **WHEN** die Seite lädt
- **THEN** ist „Transkribieren" ausgewählt und die Arbeitsfläche sichtbar

#### Scenario: Wechsel der Ansicht

- **WHEN** „Settings" gewählt wird
- **THEN** werden die Einstellungen angezeigt und „Settings" ist hervorgehoben
- **AND** die Auswahl bleibt erhalten, bis eine andere Ansicht gewählt wird

### Requirement: Req 191-2 — Admin nur in eigener Ansicht und nur für Admins

Die Admin-Funktionen DÜRFEN NICHT auf der Startseite erscheinen. Sie sind
ausschließlich in der Ansicht „Admin" verfügbar, und nur für `user.is_admin`.

#### Scenario: Startseite frei von Admin-Funktionen

- **GIVEN** ein Administrator auf der Startseite
- **THEN** enthält die Startseite keine Admin-Kacheln (Guthaben/Tier/Vacuum/
  Schlüssel)

#### Scenario: Nicht-Admin sieht kein Admin-Angebot

- **GIVEN** ein Nutzer ohne Adminrechte
- **THEN** fehlt der Menüpunkt „Admin"
- **AND** wird die Ansicht „admin" nicht gerendert

### Requirement: Req 191-3 — Ein Symbol für An- und Abmelden

Neben dem Usernamen MUSS genau ein Symbol stehen, das je nach Kontext anmeldet
oder abmeldet; getrennte Textknöpfe „Login"/„Logout" gibt es nicht mehr.

#### Scenario: Nicht angemeldet

- **GIVEN** OIDC ist aktiv und der Nutzer ist nicht angemeldet
- **THEN** zeigt das Symbol „Anmelden" (Ziel `/auth/login`)
- **AND** es trägt `title` und `aria-label` „Anmelden"

#### Scenario: Angemeldet

- **GIVEN** ein angemeldeter Nutzer
- **THEN** steht neben seinem Namen ein „Abmelden"-Symbol (Ziel `/auth/logout`)
- **AND** es trägt `title` und `aria-label` „Abmelden"
