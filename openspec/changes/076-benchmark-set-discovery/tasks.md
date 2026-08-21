# Tasks — Change 076: Benchmark-Set-Discovery

## T0 — Konfiguration (config.py)
- [ ] `BENCHMARK_SET_REPO` (Default "") ergänzen; Kommentar: Priorität
  url-Body > BENCHMARK_SET_URL env > Discovery über Repo

## T1 — Discovery (benchmark_service.py)
- [ ] `discover_sets(repo)` → GitHub-API GET /repos/{repo}/releases
  (per_page=100), Filter Tag `^benchmark-set-v(\d+)$`; Ergebnis je Release:
  {version, tag, published_at, zip_url, sha_url, zip_size}
- [ ] Cache 300 s (Klassen-/Modul-Cache mit Timestamp); API-Fehler →
  last_error setzen, [] zurückgeben (kein Crash)
- [ ] `.sha256`-Asset-Inhalt parsen: erste Hex-Zeichenfolge (sha256sum-
  Format `<hash>  <filename>` oder nacktes `<hash>`)

## T2 — Installer-Erweiterung (benchmark_service.py)
- [ ] `install_set_from_release(url=None, expected_sha=None, repo=None, version=None)`:
  - url gesetzt → Change-075-Pin-Pfad (unverändert)
  - sonst: repo (arg oder env) → discover_sets → Zielversion = version-arg
    oder max; sha aus sha_url laden (erste Hex-Folge); zip_url downloaden
  - Verifikation + Entpacken + Vollständigkeit + atomic rename (Code aus 075
    wiederverwenden — gemeinsamer `_install_zip_bytes(raw, expected_sha)`)
- [ ] `set_status()` erweitert: `repo`, `available` (aus discover_sets,
  gecacht), `pinning_mode` (true wenn BENCHMARK_SET_URL gesetzt)

## T3 — Router (routers/benchmark.py)
- [ ] `SetInstallBody` erweitert: `repo: Optional[str]`, `version: Optional[int]`
- [ ] POST /sets/install reicht repo/version durch

## T4 — Frontend
- [ ] `benchmark.ts`: `BenchmarkSetStatus` um `repo`, `available` ergänzt
  (AvailableSet: version, tag, published_at, zip_size); `installBenchmarkSet`
  akzeptiert {repo?, version?}
- [ ] `BenchmarkPage.tsx` (BenchmarkSetUpdater): Liste verfügbarer Sets —
  je Zeile Version + Datum + Größe + Button „Installieren" (disabled wenn
  ≤ aktuelle Version oder busy); neueste zuerst, „Neueste"-Badge; Hinweis
  „Pinning-Modus (env)" wenn kein Repo konfiguriert
- [ ] Erfolg/Fehler sichtbar (kein stiller Fehler)

## T5 — Tests
- [ ] Backend: discover_sets parst Releases (monkeypatch urlopen mit
  GitHub-JSON-Fixture), filtert fremde Tags, Cache (2. Aufruf kein 2. GET)
- [ ] Install via Discovery: sha aus Asset, Download, aktiviert
- [ ] version-Auswahl: installiert genau v2 obwohl v3 da
- [ ] Version ≤ aktuell → skip
- [ ] Pin-Pfad (url+sha wie 075) funktioniert weiterhin (bestehende Tests grün)
- [ ] API-Fehler → last_error + leere Liste, kein Crash
- [ ] Frontend: Verfügbarkeits-Liste rendert, Install-Button je Release,
  Pinning-Hinweis ohne Repo
- [ ] Gates: tsc --noEmit, npm test, Backend-Suite GESAMT fail=0

## T6 — Release/Assets + Doku
- [ ] Release v1: `.sha256`-Asset `benchmark-set-v1.zip.sha256` hochladen
  (Inhalt `<sha>  benchmark-set-v1.zip`)
- [ ] README (GitHub): Konvention um .sha256-Asset + Discovery-Env ergänzen
- [ ] `docs/benchmark/admin.md`: Discovery statt URL-Pinning dokumentieren
