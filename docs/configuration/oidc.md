# OIDC-Auth

Ohne OIDC läuft PolySchnack als **Shared Space**: jede\*r kann hochladen und
transkribieren, alles ist öffentlich und wird nach `PUBLIC_RETENTION_MINUTES`
automatisch gelöscht.

Mit OIDC bekommt jede\*r eingeloggte User einen **privaten Workspace** (eigene
Aufnahmen, fremde unsichtbar). Der Admin-Bereich (Service-Start/Stop,
Backend-Wechsel) setzt OIDC zwingend voraus — ohne Login gibt es keine Admins.

## Aktivierung

**Fertiges Compose-Overlay mit Dummy-Werten:** `compose.oidc.yml`

```bash
docker compose -f compose.yml -f compose.oidc.yml up -d
```

Alle Werte dort sind DUMMY (Client-ID/Secret, `auth.example.com`,
`admin@example.com`) — vor Produktion ersetzen.

| Variable | Beispiel | Bedeutung |
|----------|----------|-----------|
| `OIDC_CLIENT_ID` | `polyschnack` | Client-ID beim Identity Provider |
| `OIDC_CLIENT_SECRET` | `…` | Client-Secret beim IdP (Confidential Client) |
| `OIDC_ISSUER` | `https://auth.example.com` | Issuer-URL (Keycloak, Authentik, …) — **OIDC ist aktiv, sobald Client-ID + Issuer gesetzt sind** |
| `OIDC_SCOPE` | `openid profile email` | Standard; `email` wird benötigt, wenn Admins per E-Mail matchen sollen |
| `SESSION_SECRET` | zufälliger langer String | Signiert die Session-Cookies — **unbedingt setzen** |
| `BASE_URL` | `https://polyschnack.example.com` | Externe URL der App; **der OIDC-Redirect läuft immer hierhin** |

## Einmalig beim IdP registrieren

- Redirect-URI: `https://<BASE_URL>/auth/callback` (exakt, ohne Trailing-Slash)
- Flow: Authorization Code + PKCE (Confidential Client)
- Für Admin-Match per Gruppe: `groups`-Claim im Userinfo (Keycloak:
  Gruppen-Mapper; Authentik: standardmäßig enthalten)

## Login-Ablauf

`GET /auth/login` → Redirect zum IdP → `GET /auth/callback`
(setzt Session, speichert `is_admin`) → zurück zur App.
`GET /auth/logout` löscht die Session.

**Eigene User-ID finden:** eingeloggt `GET /auth/me` → `sub`, `email`, `name`,
`is_admin`.

## Admins designieren

- `POLYSCHNACK_ADMINS` — Komma-Liste von `sub`-IDs **oder** E-Mails
- `POLYSCHNACK_ADMIN_GROUPS` — Komma-Liste von OIDC-Gruppennamen

Beide wirken **unabhängig voneinander** (ODER-Verknüpfung):

1. **sub/email-Liste:** Beim Login wird der User in der DB angelegt bzw.
   aktualisiert. Der Check vergleicht `user.sub` und `user.email` exakt.
2. **Gruppen:** Beim Login holt die App die Userinfo vom IdP
   (`GET {issuer}/userinfo`) und bildet die Schnittmenge aus
   `userinfo["groups"]` und der Komma-Liste. Ist sie nicht leer → Admin.

!!! warning "Änderungen an Admin-Variablen"
    `is_admin` wird einmalig beim Login berechnet und in der Session gecacht.
    Nach Änderungen der Admin-Variablen **neu einloggen** (Logout → Login).
    Ohne aktives OIDC liefert `require_admin` immer 403.
