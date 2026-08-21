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

## Benchmark-Set automatisch installieren (Change 075)

Die Webapp kann sich neue ASR-Testsets selbst von einem GitHub-Release holen —
kein manuelles Entpacken auf der Box mehr.

**Release-Format** (`tilllt/polyschnack-benchmark-data`, Tag `benchmark-set-v<N>`):

```
benchmark-set-v<N>.zip
├── manifest.json        # version, testset_version, supersedes, samples[]
├── audio/<sid>.wav      # 16 kHz mono
└── preview/<sid>.mp3    # 128 kbps
```

**Konfiguration** (compose.yml, env):

```yaml
BENCHMARK_SET_URL: "https://github.com/tilllt/polyschnack-benchmark-data/releases/download/benchmark-set-v1/benchmark-set-v1.zip"
BENCHMARK_SET_SHA256: "4755be03f8d03dcae4b885c2cf7117d29050f87962bf099e3610b9911828891d"
BENCHMARK_SET_AUTO_INSTALL: "true"   # optional: beim Start prüfen/installieren
```

Ohne URL ist der Mechanismus inaktiv; der manuelle Deploy (tar.gz → entpacken)
funktioniert unverändert.

**Ablauf beim Install:**

1. Download (HTTPS-Pflicht, 300 s Timeout)
2. **SHA256-Verifikation** — Mismatch → Abbruch, kein Zustand geändert
3. `manifest.version` ≤ aktuell → „bereits installiert" (nie überschreiben)
4. Sicheres Entpacken (nur `manifest.json`/`audio/`/`preview/`, Traversal abgelehnt)
5. Vollständigkeitsprüfung (WAVs/Previews == Samples)
6. Atomic rename nach `versions/v{N}` → neue aktive Version

**API:**

- `GET /api/benchmark/sets` → Status (öffentlich, SHA nur als Präfix)
- `POST /api/benchmark/sets/install` → Install (Admin-only)

**GUI:** Admin-Sektion „Benchmark-Set" auf der Benchmark-Seite — Status +
Button „⟳ Neues Set installieren". Fehler werden sichtbar angezeigt.

Beide Routen erfordern `require_admin` (403 ohne OIDC oder ohne Admin-Session).
