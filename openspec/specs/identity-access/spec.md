# Identity & Access

## Purpose

Benutzer identifizieren (OIDC oder anonymes Session-Cookie oder API-Key),
Admins bestimmen, Zugriffsrechte durchsetzen.

## Requirements

### Req 1: OIDC-Login

- **Ablauf:** `/auth/login` → Redirect zum Provider; Callback legt
  `session["user_id"]`, `session["is_admin"]` (aus Env-Admins
  `POLYSCHNACK_ADMINS` oder Gruppen-Claim `POLYSCHNACK_ADMIN_GROUPS`).
  Ohne OIDC_ENABLED fällt alles auf anonym zurück.
- **Ergebnis:** `GET /api/me` liefert `{authenticated, name, is_admin, kind}`.
- **Architektur:** `routers/auth.py`, `routers/users.py` (me), `deps.py`.

#### Scenario: Login über authentik

- **Akteure:** Benutzer ohne Session.
- **Eingaben:** Klick auf „Login".
- **Ergebnis:** Redirect zum Provider, Callback setzt Session; `me` zeigt
  Namen + `is_admin` (bei Gruppen-Match).

### Req 2: Anonyme Sessions (Shared Space)

- **Ablauf:** Ohne Login erzeugt `app/anon_session.py::ensure_anonymous_user`
  einen User `kind="anonymous"` mit zufälligem Anzeigenamen (z. B. „Funny
  Rabbit Wizard"), gebunden an ein Session-Cookie (`anon_user_id`).
  `current_uid(request, session)` löst die Identität für jeden Request auf
  (OIDC > anon-Cookie).
- **Ergebnis:** Anonyme User können transkribieren (öffentliche Aufnahmen),
  aber keine paid-Pfade, keine API-Keys, keine BYOK-/LLM-Templates.
- **Architektur:** `anon_session.py`, `anon_names.py`; `last_seen_at`-Update
  max. alle 60 s (kein Write pro Request).

#### Scenario: Erster Besuch ohne Login

- **Akteure:** Browser ohne Cookie.
- **Eingaben:** GET /api/recordings.
- **Ergebnis:** Anon-User wird erzeugt (Random-Name), Cookie gesetzt;
  Liste zeigt öffentliche Aufnahmen.

### Req 3: API-Keys (Bearer)

- **Ablauf:** `POST /api/keys` erzeugt einen Key (SHA-256-Hash in der DB,
  Klartext nur einmal); `GET/PUT/DELETE /api/keys` verwalten (level
  read|write|full). Request mit `Authorization: Bearer <token>` wird als
  Identität des Key-Inhabers geführt, **gedeckelt** auf `key_level`.
- **Ergebnis:** Routen sehen alles des Inhabers, aber maximal bis zur
  Key-Ebene (read-Key kann nicht editieren).
- **Architektur:** `routers/keys.py`, `identity.py` (current_identity →
  Bearer zuerst, dann Session), `permissions.py::get_access_level(cap=…)`.

#### Scenario: API-Key mit read-Level

- **Akteure:** Registrierter User mit `read`-Key.
- **Eingaben:** `GET /api/recordings` mit Bearer; danach PATCH eines Segments.
- **Ergebnis:** Liste 200; PATCH → 403 (Cap `read` < `write`).

### Req 4: Admin

- **Ablauf:** `POLYSCHNACK_ADMINS` (Sub-Liste) ODER `POLYSCHNACK_ADMIN_GROUPS`
  (Gruppen-Claim). `require_admin` auf dem Admin-Router → 403 ohne OIDC/Admin.
  Env-Änderungen wirken erst nach neuem Login.
- **Architektur:** `deps.py::require_admin`, `routers/admin.py`.

#### Scenario: Admin-Panel

- **Akteure:** Admin (Env oder Gruppe).
- **Eingaben:** `GET /api/admin/env-settings`, `PUT /api/admin/config`.
- **Ergebnis:** 200; Env-Optionen read-only mit ENV-Badge; nur
  `DATA_DIR/config.json`-Backend editierbar. Nicht-Admin → 403.
