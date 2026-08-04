# Benchmark Admin-Workflow

Nur für Admins (OIDC-Login + `POLYSCHNACK_ADMINS`/`-GROUPS`).

## Sample ablehnen → Auto-Ersatz

**✕ Ablehnen** pro Sample:

1. Das Sample wird aus der öffentlichen Liste genommen (`status: rejected`)
2. **Auto-Ersatz** wird aus dem CV-Pool gewählt (gleiche Kategorie-Kriterien,
   deterministischer Seed, verbrauchte IDs ausgeschlossen)
3. **Neue Version vN+1** wird erzeugt — Manifeste sind **immutable**,
   die History bleibt über eine `supersedes`-Kette erhalten

## Sample editieren

**Edit** pro Sample → Referenztext ändern (in-place, `updated_at`).

## Versions-History

Unter `/api/benchmark/versions`:

```json
{ "versions": [{ "version": 2, "created_at": "...", "active": 1, "rejected": 1 }] }
```

## API

- `POST /api/benchmark/samples/{id}/reject` → `{ new_version, replacement }`
- `POST /api/benchmark/samples/{id}/edit` → `{ ok, sample }`

Beide Routen erfordern `require_admin` (403 ohne OIDC oder ohne Admin-Session).
