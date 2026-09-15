# Templates (Marktplatz)

## ADDED Requirements

### Requirement: Marktplatz

- **Ablauf:** Öffentliche Templates sind unter dem Tab „Community" im 
  Export-Dialog sichtbar und durchsuchbar.
- **Eingaben:** `GET /api/templates?visibility=public&tag=highlight&q=suchtext`.
- **Ausgaben:** Paginierte Liste öffentlicher Templates mit Name, Ersteller, 
  Beschreibung, Tags, Credit-Kosten, Vorschau und Download-Zähler.
- **Ergebnis:** Jeder angemeldete User kann öffentliche Templates sehen, 
  ohne sie zu installieren.
- **Architektur:** `routers/templates.py`; DB-Filter `visibility=public`.

#### Scenario: Öffentliches Template finden

- **Akteure:** Angemeldeter User.
- **Eingaben:** `GET /api/templates?visibility=public&tag=karaoke`.
- **Ergebnis:** 200 mit max. 20 Treffern pro Seite, Gesamtzahl in 
  `X-Total-Count`.

### Requirement: Installation und Cost

- **Ablauf:** Ein User installiert ein öffentliches Template in seine 
  Bibliothek, wobei gegebenenfalls Credits abgebucht werden.
- **Eingaben:** `POST /api/templates/{id}/install`.
- **Ausgaben:** 200 mit `template_installation_id`.
- **Ergebnis:** 
  - Kostenlos (`credit_cost=0`): Template sofort in der Bibliothek.
  - Credits (`credit_cost>0`): Abbuchung vom Guthaben, 10 % Plattform-Anteil, 
    Rest an den Ersteller.
  - Unzureichendes Guthaben: 402 `{"error": "insufficient_credits", 
    "required": 5, "balance": 2}`.
- **Architektur:** `routers/templates.py` → `credit_transfer()` →

#### Scenario: Kostenloses Template installieren

- **Akteure:** Angemeldeter User.
- **Eingaben:** `POST /api/templates/00000000-0000-0000-0000-000000000001/install`.
- **Ergebnis:** 200; Template erscheint in der Bibliothek.

#### Scenario: Credits-Template installieren

- **Akteure:** Angemeldeter User mit Guthaben ≥ 5 Credits.
- **Eingaben:** `POST /api/templates/…/install`.
- **Ergebnis:** 200; 4,5 Credits an Ersteller, 0,5 Plattform-Anteil; 
  Template in Bibliothek.

### Requirement: Teilen per Share-Link

- **Ablauf:** Ein Template mit `visibility=link_only` kann nur über einen 
  token-basierten Share-Link installiert werden.
- **Eingaben:** `POST /api/templates/{id}/share` → erzeugt UUID-Token.
- **Ausgaben:** `{"share_url": "/templates/share/{token}"}`.
- **Ergebnis:** Der Link ist nicht öffentlich auffindbar; jeder mit dem 
  Link kann installieren (z. B. zum Testen vor Veröffentlichung).
- **Architektur:** DB-Feld `share_token`; `GET /api/templates/share/{token}` 
  → Template-Detail + Install-Button.

#### Scenario: Share-Link erstellen

- **Akteure:** Template-Ersteller mit `visibility=link_only`.
- **Eingaben:** `POST /api/templates/{id}/share`.
- **Ergebnis:** 200 mit neuem Token; alter Token wird ungültig.

#### Scenario: Share-Link installieren

- **Akteure:** Angemeldeter User mit gültigem Share-Link.
- **Eingaben:** `GET /api/templates/share/abc-123-xyz`.
- **Ergebnis:** 200 mit Template-Detail + Install-Button.