# Change Proposal 003 — Anonyme Sessions & Retention

**Status:** Implemented (retroaktiv)

## Why
- Shared Space soll ohne Login funktionieren, Daten aber automatisch
  verschwinden (Datenschutz).

## What
- `User.kind` (oidc|anonymous), `display_name` (zufällig), `last_seen_at`.
- Cookie-gebundene anon-Sessions (`anon_session.py::ensure_anonymous_user`,
  `current_uid`); alle Router auf die Session-Variante umgestellt.
- Retention: Sliding 15 min (`POLYSCHNACK_ANON_RETENTION_MINUTES`),
  Sweep-Thread alle 5 min löscht anon-User + Recordings + Shares + Versionen.
- Harte anon-Limits (Dauer/Upload/Disk) in `anon_limits.py`.

## Changes
- Neu: `anon_session.py`, `anon_names.py`, `retention.py`, `anon_limits.py`;
  Tests `test_anon*.py`, `test_retention.py`.
- Geändert: `models.py`, `config.py`, `main.py`, alle Router
  (Identitätsauflösung `_current_user(request, session)`).

## Downgrade
- Retention deaktivieren → Sweep-Thread nicht starten; anon-User bleiben.
