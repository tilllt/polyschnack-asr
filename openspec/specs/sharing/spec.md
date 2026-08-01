# Sharing

## Purpose

Aufnahmen zwischen registrierten Usern teilen — mit abgestuften Rechten
(read | write | full) und transparenter Sichtbarkeit in der Liste.

## Requirements

### Req 1: Share-CRUD

- **Ablauf:** `POST /api/shares` (recording_id, shared_with, level);
  `GET /api/shares`, `PUT/DELETE /api/shares/{id}`. Nur der Besitzer
  (`user_id` der Aufnahme) verwaltet Shares; Fremde → 403/404.
- **Eingaben:** `level ∈ {read, write, full}` (Pydantic-Literal, sonst 422).
- **Architektur:** `routers/shares.py`; UniqueConstraint
  (recording_id, shared_with) — doppelte Shares werden aktualisiert.

#### Scenario: Besitzer teilt mit write

- **Akteure:** Besitzer A, User B.
- **Eingaben:** A erstellt Share(rec, B, "write").
- **Ergebnis:** B sieht die Aufnahme mit Badge „geteilt", kann Segmente
  editieren (`write`), aber nicht löschen (`full` nötig). A kann widerrufen.

### Req 2: Zugriff durchsetzen

- **Ablauf:** `permissions.py::ensure_access(session, rec, uid, level, cap=…)`
  zentral in allen Routen. Auflösung: Besitzer > Share-Level > öffentlich
  (legacy-public: read für anonyme) > nichts.
- **Ergebnis:** Unterschrittenes Level → 403. `cap` (API-Key-Level) deckelt
  zusätzlich.

#### Scenario: Fremder ohne Share

- **Akteure:** User C (kein Share).
- **Eingaben:** `GET /api/recordings/{id}`.
- **Ergebnis:** 403 — die Aufnahme erscheint nicht in C's Liste.

### Req 3: Sichtbarkeit & Serien-Felder

- **Ablauf:** Listen-Endpoint `GET /api/recordings` liefert Shares nur für
  eingeloggte User (`include_shares=uid is not None`) und je Aufnahme
  `access_level` (read/write/full/owner/public/none) + `shared_with`-Namen.
- **Architektur:** `routers/recordings.py` (list), `_recording_to_dict`.

#### Scenario: Geteilte Aufnahme in der Liste

- **Akteure:** User B.
- **Eingaben:** GET /api/recordings.
- **Ergebnis:** Geteilte Aufnahme mit `access_level: "write"` und
  Share-Namen sichtbar (nur für eingeloggte User).
