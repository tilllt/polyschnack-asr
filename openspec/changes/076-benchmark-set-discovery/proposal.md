# Change 076: Benchmark-Set-Discovery — neue Sets selbst finden statt env-URL

## Problem

Change 075 hat den Install-Mechanismus gebaut, aber die Quelle ist eine
**env-hardcodierte URL** (`BENCHMARK_SET_URL` + `BENCHMARK_SET_SHA256`).
Damit ist der GUI-Button nur ein einmaliger Klick auf das eine fixe Paket:

- Neues Set v2 → compose.yml editieren, Container neu starten — genau das
  manuelle Umständliche, das der Auto-Update beseitigen sollte.
- Die Webapp „weiß" nicht, dass es ein neueres Release gibt.

## Ziel

Die Webapp **findet neue Benchmark-Sets selbst**: sie fragt die GitHub-API
nach Releases im Repo (`tilllt/polyschnack-benchmark-data`), erkennt
`benchmark-set-v<N>`, zeigt die verfügbaren Versionen in der GUI an und
installiert die gewählte (oder neueste) per Klick. Env braucht nur noch das
**Repo** (einmalig) — kein URL/SHA-Pinning mehr nötig, bleibt aber als
Fallback möglich (private/gespiegelte Quellen).

## Design

### Release-Konvention (erweitert)

Jedes Release `benchmark-set-v<N>` hat **zwei** Assets:

```
benchmark-set-v<N>.zip            # das Set (wie Change 075)
benchmark-set-v<N>.zip.sha256     # SHA256 als Textdatei (Inhalt: <hash>  <dateiname>)
```

Die SHA liegt **beim Release im selben Repo** — für Integrität (Download-
Abbruch/Korruption/Man-in-the-Middle über HTTPS) ausreichend; für
absolutes Trust-Anker-Pinning bleibt `BENCHMARK_SET_SHA256` als env-Option
erhalten (dann wird NUR diese SHA akzeptiert).

### Konfiguration (env, ersetzt URL-Pinning als Default)

```yaml
BENCHMARK_SET_REPO: "tilllt/polyschnack-benchmark-data"  # Default leer
# optional weiterhin wirksam (Fallback/Pinning):
BENCHMARK_SET_URL: ""      # wenn gesetzt: direkter Install (kein Discovery)
BENCHMARK_SET_SHA256: ""   # wenn gesetzt: zusätzliche Verifikation/Pin
BENCHMARK_SET_AUTO_INSTALL: "false"
```

Priorität beim Install:
1. Explizite `url` im Request (Admin-Override) → wie Change 075
2. `BENCHMARK_SET_URL` env (Pinning-Fallback) → wie Change 075
3. Sonst: **Discovery** über `BENCHMARK_SET_REPO` → neueste (oder gewählte) Version

### Backend (benchmark_service.py)

- `discover_sets(repo)` → GET `https://api.github.com/repos/{repo}/releases`
  (per_page=100), filtert Tags `benchmark-set-v<N>`, liefert je Release:
  `{version, tag, published_at, zip_url, sha_url, zip_size}`
  - **Cache** (5 min, In-Memory) — GitHub-API-Rate-Limit (60/h unauthenticated)
  - Fehler (Netz/API) → `last_error`, kein Crash
- `install_set_from_release(url=None, expected_sha=None, repo=None, version=None)`:
  - url/expected_sha wie gehabt (Pin-Pfad)
  - sonst: `discover_sets(repo)` → Zielversion (explizit oder max),
    SHA aus `.sha256`-Asset laden, Download + Verifikation, dann gleicher
    Ablauf wie 075 (sicheres Entpacken, Vollständigkeit, atomic rename)
  - SHA aus Asset: erste Hex-Zeichenfolge in der Datei (sha256sum-Format
    `<hash>  <filename>` oder nur `<hash>`)
- `set_status()` erweitert: `repo`, `available: [discover_sets-Ergebnis]`
  (nur Version/Tag/Datum/Größe — keine URLs nötig im öffentlichen Status;
  URLs sind öffentlich, dürfen also mit)

### Router

- `GET /api/benchmark/sets` → Status + `available` (gecacht)
- `POST /api/benchmark/sets/install` → Body optional:
  `{url?, sha256?, repo?, version?}` — ohne url: Discovery-Pfad;
  `version` wählt explizite Release-Version

### Frontend (BenchmarkPage, Admin-Sektion „Benchmark-Set")

- Liste **verfügbarer Sets** (aus `available`): je Zeile Version, Datum,
  Größe, Button „Installieren" (oder „Aktuell" bei ≤ installierter Version)
- Bei mehreren: neueste zuerst, Highlight „Neueste"
- Klick → `installBenchmarkSet({version})` → Erfolg/Fehler sichtbar
- Status-Zeile: Repo, aktuelle Version, letzter Fehler
- Fallback: wenn nur URL env (kein Repo) → Hinweis „Pinning-Modus (env)"

### Sicherheit

- Download nur HTTPS; SHA-Pflicht (aus Asset ODER env); Traversal-Schutz,
  Vollständigkeitsprüfung, atomic rename — unverändert aus Change 075
- Discovery liest nur öffentliche Release-Metadaten (keine Secrets)
- Rate-Limit-freundlich: Cache 5 min; kein Polling-Loop

## Nicht-Ziel

- Kein automatisches Polling/Install ohne Admin-Aktion (außer
  AUTO_INSTALL=true beim Start, wie 075)
- Kein automatisierter Benchmark-Neulauf nach Install (Submit bleibt manuell/CI)
- Kein Löschen alter Versionen

## Betroffene Dateien

- `webapp/app/benchmark_service.py` (discover_sets, Installer-Erweiterung)
- `webapp/app/routers/benchmark.py` (Body erweitert)
- `webapp/app/config.py` (BENCHMARK_SET_REPO)
- `webapp/frontend/src/benchmark.ts` (Typen, installBenchmarkSet)
- `webapp/frontend/src/components/BenchmarkPage.tsx` (Verfügbarkeits-Liste)
- `webapp/tests/test_benchmark_router.py` (Discovery-Tests)
- `webapp/frontend/src/components/BenchmarkPage.test.tsx`
- `docs/benchmark/admin.md`

## Erfolgskriterien

- [ ] Discovery liefert Releases aus dem Repo (gecacht, Rate-Limit-sicher)
- [ ] Install ohne env-URL: SHA aus `.sha256`-Asset, Download, aktivieren
- [ ] `version`-Auswahl installiert genau diese Release-Version
- [ ] Version ≤ aktuell → skip (nie überschreiben)
- [ ] env-URL/SHA-Pin (Change 075-Pfad) funktioniert weiterhin
- [ ] GUI zeigt verfügbare Sets + installiert per Klick; Fehler sichtbar
- [ ] Tests: Backend-Suite fail=0, Frontend grün, tsc 0
