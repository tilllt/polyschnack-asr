# Change 171 — OIDC-Overlay nur noch auf explizite Anforderung

**Status:** Proposed

## Befund (2026-08-31)

`polyschnack-manage.sh` aktiviert das OIDC-Overlay automatisch, sobald
echte Credentials in `compose.oidc.yml` stehen (Zeile 147-152). Auf der
KI-Box liegt `compose.oidc.yml` mit echten Credentials (lokal, nicht in
Git) → jeder `update`/`start`-Lauf schaltet OIDC-Login an. Anforderung:
Stack soll **ohne** OIDC-Overlay laufen („Wieder ohne oidc overlay").

## Lösung

OIDC-Overlay nur noch laden, wenn in der `.env` explizit
`POLYSCHNACK_OIDC=1` gesetzt ist. Default bleibt aus.

## Betroffene Dateien

- `polyschnack-manage.sh` (Overlay-Auswahl)
