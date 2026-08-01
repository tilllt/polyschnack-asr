# Change Proposal 004 — API-Keys mit Rechte-Deckel

**Status:** Implemented (retroaktiv)

## Why
- Maschineller Zugriff (Scripts/CI) auf die API ohne Session-Cookie, mit
  bewusst begrenzten Rechten.

## What
- `ApiKey` (user_id, name, level read|write|full, SHA-256-Hash, last_used_at);
  CRUD `/api/keys` (Klartext nur bei Erzeugung).
- `identity.py::current_identity` — Bearer-Key > OIDC-Session > anon-Cookie;
  `key_level` deckelt `ensure_access`/`get_access_level` (cap).
- Alle Router auf `current_identity`-gestützte Auflösung umgestellt.

## Changes
- Neu: `identity.py`, `routers/keys.py`; Tests `test_apikeys.py`,
  `test_apikey_access.py`.
- Geändert: `permissions.py` (cap), alle Router + Test-Patches.

## Downgrade
- Keys entfernen → nur Session-Auth; cap-Parameter entfällt.
