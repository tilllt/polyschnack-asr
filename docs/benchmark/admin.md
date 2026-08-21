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

## Benchmark-Set automatisch installieren (Change 075/076)

Die Webapp kann sich neue ASR-Testsets selbst holen — kein manuelles
Entpacken auf der Box mehr. **Change 076: git-basiert und host-agnostisch**
(kein GitHub-Hardcode): Quelle ist ein beliebiges Git-Repo (GitHub, GitLab,
selbst gehostet, lokaler Pfad), erkannt per `git ls-remote --tags`.

**Repo-Konvention** (z. B. `tilllt/polyschnack-benchmark-data`, Tag
`benchmark-set-v<N>`):

```
benchmark-set-v<N>.zip            # manifest.json + audio/*.wav + preview/*.mp3
benchmark-set-v<N>.zip.sha256     # SHA256 (sha256sum-Format) — Integrität
```

**Konfiguration** (compose.yml, env) — **git-Modus (Default, Change 076)**:

```yaml
BENCHMARK_SET_GIT_URL: "https://github.com/tilllt/polyschnack-benchmark-data.git"
BENCHMARK_SET_AUTO_INSTALL: "true"   # optional: beim Start prüfen/installieren
```

Die Webapp listet `benchmark-set-v<N>`-Tags per `git ls-remote --tags`
(5-min-Cache) und installiert per Klick: `git clone --depth 1 --branch
benchmark-set-v<N> --single-branch` → SHA256 aus der `.sha256`-Datei.

**Pinning-Modus (optional, Change 075):** statt git eine feste HTTPS-URL+SHA:

```yaml
BENCHMARK_SET_URL: "https://…/benchmark-set-v1.zip"
BENCHMARK_SET_SHA256: "4755be03f8d03dcae4b885c2cf7117d29050f87962bf099e3610b9911828891d"
```

Priorität: Body-URL (Admin) > `BENCHMARK_SET_URL` (Pin) > git-URL.

Ohne Quelle (kein git, keine URL) ist der Mechanismus inaktiv; der manuelle
Deploy (tar.gz → entpacken) funktioniert unverändert.

**Ablauf beim Install:**

1. **Discovery:** `git ls-remote --tags` (5-min-Cache) bzw. Pinning-URL aus env
2. **Download:** `git clone --depth 1 --branch <tag> --single-branch`
   (HTTPS/SSH/lokal, 300 s Timeout) bzw. HTTPS-Download beim Pin
3. **SHA256-Verifikation** — aus `.sha256`-Datei im Repo (git) oder env-SHA
   (Pin); Mismatch → Abbruch, kein Zustand geändert
4. `manifest.version` ≤ aktuell → „bereits installiert" (nie überschreiben)
5. Sicheres Entpacken (nur `manifest.json`/`audio/`/`preview/`, Traversal abgelehnt)
6. Vollständigkeitsprüfung (WAVs/Previews == Samples)
7. Atomic rename nach `versions/v{N}` → neue aktive Version

**API:**

- `GET /api/benchmark/sets` → Status + verfügbare Tags (öffentlich, SHA nur als Präfix)
- `POST /api/benchmark/sets/install` → Install (Admin-only); Body optional
  `{url, sha256}` = Pin, `{git_url, version}` = git

**GUI:** Admin-Sektion „Benchmark-Set" auf der Benchmark-Seite — Status +
Button „⟳ Neues Set installieren". Fehler werden sichtbar angezeigt.

Beide Routen erfordern `require_admin` (403 ohne OIDC oder ohne Admin-Session).
