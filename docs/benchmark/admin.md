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
benchmark-set-v<N>.zip            # manifest.json + audio/*.wav + preview/*.mp3
benchmark-set-v<N>.zip.sha256     # SHA256 (sha256sum-Format) — Integrität
```

**Konfiguration** (compose.yml, env) — **Discovery-Modus (Default, Change 076)**:

```yaml
BENCHMARK_SET_REPO: "tilllt/polyschnack-benchmark-data"
BENCHMARK_SET_AUTO_INSTALL: "true"   # optional: beim Start prüfen/installieren
```

Die Webapp listet `benchmark-set-v<N>`-Releases des Repos (GitHub-API, 5-min-Cache)
und installiert per Klick — SHA256 wird je Release aus dem `.sha256`-Asset geladen.

**Pinning-Modus (optional, Change 075):** statt Repo eine feste URL+SHA:

```yaml
BENCHMARK_SET_URL: "https://github.com/tilllt/polyschnack-benchmark-data/releases/download/benchmark-set-v1/benchmark-set-v1.zip"
BENCHMARK_SET_SHA256: "4755be03f8d03dcae4b885c2cf7117d29050f87962bf099e3610b9911828891d"
```

Priorität: Body-URL (Admin) > `BENCHMARK_SET_URL` (Pin) > Discovery über Repo.

Ohne Quelle (kein Repo, keine URL) ist der Mechanismus inaktiv; der manuelle
Deploy (tar.gz → entpacken) funktioniert unverändert.

**Ablauf beim Install:**

1. **Discovery:** GitHub-API → `benchmark-set-v<N>`-Releases (5-min-Cache)
   bzw. Pinning-URL aus env
2. Download (HTTPS-Pflicht, 300 s Timeout)
3. **SHA256-Verifikation** — aus `.sha256`-Asset (Discovery) oder env-SHA
   (Pin); Mismatch → Abbruch, kein Zustand geändert
4. `manifest.version` ≤ aktuell → „bereits installiert" (nie überschreiben)
5. Sicheres Entpacken (nur `manifest.json`/`audio/`/`preview/`, Traversal abgelehnt)
6. Vollständigkeitsprüfung (WAVs/Previews == Samples)
7. Atomic rename nach `versions/v{N}` → neue aktive Version

**API:**

- `GET /api/benchmark/sets` → Status + verfügbare Releases (öffentlich, SHA nur als Präfix)
- `POST /api/benchmark/sets/install` → Install (Admin-only); Body optional
  `{url, sha256}` = Pin, `{repo, version}` = Discovery

**GUI:** Admin-Sektion „Benchmark-Set" auf der Benchmark-Seite — Status +
Button „⟳ Neues Set installieren". Fehler werden sichtbar angezeigt.

Beide Routen erfordern `require_admin` (403 ohne OIDC oder ohne Admin-Session).
