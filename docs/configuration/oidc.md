# OIDC-Auth

Ohne OIDC läuft PolySchnack als **Shared Space**: jede\*r kann hochladen und
transkribieren, alles ist öffentlich und wird nach `PUBLIC_RETENTION_MINUTES`
automatisch gelöscht.

Mit OIDC bekommt jede\*r eingeloggte User einen **privaten Workspace** (eigene
Aufnahmen, fremde unsichtbar). Der Admin-Bereich (Service-Start/Stop,
Backend-Wechsel) setzt OIDC zwingend voraus — ohne Login gibt es keine Admins.

## Aktivierung

**Fertiges Compose-Overlay:** `compose.oidc.yml`

```bash
docker compose -f compose.yml -f compose.oidc.yml up -d
```

Alle Werte im Overlay werden aus der **`.env`-Datei im Repo-Root interpoliert**
(docker compose liest sie automatisch). Die im Overlay hinterlegten Defaults
sind DUMMY-Werte — die echten Werte gehören in die `.env`:

```bash
# .env (Repo-Root, neben compose.yml)
OIDC_CLIENT_ID=polyschnack
OIDC_CLIENT_SECRET=…
OIDC_ISSUER=https://auth.example.com
SESSION_SECRET=…
BASE_URL=https://polyschnack.example.org
POLYSCHNACK_ADMINS=<sub-oder-email>
POLYSCHNACK_ADMIN_GROUPS=
```

!!! warning "Warum wirkt meine .env nicht?"
    Eine Variable aus der `.env` erreicht den Container **nur**, wenn sie im
    `environment:`-Block eines compose-Files referenziert wird
    (`${VAR:-default}`). Reine `.env`-Einträge ohne Referenz werden ignoriert —
    deshalb standen die OIDC-/Admin-Werte früher hart im Overlay. Seit der
    Umstellung auf Interpolation genügt es, die Werte in die `.env` zu
    schreiben und `docker compose -f compose.yml -f compose.oidc.yml up -d`
    neu auszuführen.

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

!!! tip "Die Variable heißt `POLYSCHNACK_ADMINS` — nicht `SUB`"
    Die Env-Variable für die Admin-Liste heißt exakt `POLYSCHNACK_ADMINS`.
    Ein Eintrag wie `SUB=<wert>` in der `.env` wird vom Code **nie gelesen**.
    Richtig: `POLYSCHNACK_ADMINS=<sub-oder-email>`. Den eigenen `sub` findet
    man eingeloggt über `GET /auth/me` (Feld `sub`).

Beide wirken **unabhängig voneinander** (ODER-Verknüpfung):

1. **sub/email-Liste:** Beim Login wird der User in der DB angelegt bzw.
   aktualisiert. Der Check vergleicht `user.sub` und `user.email` exakt.
2. **Gruppen:** Beim Login holt die App die Userinfo vom IdP
   (`GET {issuer}/userinfo`) und bildet die Schnittmenge aus
   `userinfo["groups"]` und der Komma-Liste. Ist sie nicht leer → Admin.

!!! warning "Änderungen an Admin-Variablen"
    `is_admin` wird beim Login berechnet und in der Session gecacht, aber
    **bei jedem `/auth/me`-Aufruf frisch gegen die Env nachgezogen** — eine
    Änderung der Admin-Variablen wirkt also nach einem Seiten-Reload (bzw.
    nach `docker compose up -d` für Env-Änderungen, die den Container neu
    erstellen). Ohne aktives OIDC liefert `require_admin` immer 403.
