# Tasks — Change 076: Benchmark-Set-Discovery (git-basiert)

## T0 — Konfiguration (config.py)
- [ ] `BENCHMARK_SET_GIT_URL` (Default "") ergänzen; Kommentar: Priorität
  Body-url > BENCHMARK_SET_URL env > git-URL (BENCHMARK_SET_GIT_URL)

## T1 — Discovery (benchmark_service.py)
- [ ] `discover_sets(git_url)` → `git ls-remote --tags <url>` via subprocess
  (timeout 60, GIT_TERMINAL_PROMPT=0), Filter Tag `^benchmark-set-v(\d+)$`;
  Ergebnis je Version: {version, tag}
- [ ] Cache 300 s; Fehler → RuntimeError (kein Crash)
- [ ] `_parse_sha_asset` bleibt (sha256sum-Format `<hash>  <filename>`)

## T2 — Installer-Erweiterung (benchmark_service.py)
- [ ] `install_set_from_release(url=None, expected_sha=None, git_url=None, version=None)`:
  - url gesetzt → Change-075-Pin-Pfad (unverändert)
  - sonst: git_url (arg oder env) → discover_sets → Zielversion = version-arg
    oder max → `git clone --depth 1 --branch benchmark-set-v<N> --single-branch
    <git_url> <tmp>` → `benchmark-set-v<N>.zip` + `.zip.sha256` aus Checkout
    lesen → SHA parsen → Kern `_install_zip_bytes(raw, sha)`
- [ ] `set_status()` erweitert: `git_url`, `available` (aus discover_sets,
  gecacht), `pinning_mode` (true wenn BENCHMARK_SET_URL gesetzt)

## T3 — Router (routers/benchmark.py)
- [ ] `SetInstallBody`: `repo` → `git_url` (Optional[str]), `version` bleibt
- [ ] POST /sets/install reicht git_url/version durch

## T4 — Frontend
- [ ] `benchmark.ts`: `BenchmarkSetStatus` um `git_url` + `available`
  (AvailableSet: version, tag); `installBenchmarkSet(url, sha256, gitUrl, version)`
- [ ] `BenchmarkPage.tsx` (BenchmarkSetUpdater): Liste verfügbarer Sets —
  je Zeile Version + Button „Installieren" (disabled wenn ≤ aktuelle oder
  busy); neueste zuerst, „Neueste"-Badge; „Neuestes Set installieren"-Button;
  Pinning-Hinweis wenn kein git_url
- [ ] Erfolg/Fehler sichtbar (kein stiller Fehler)

## T5 — Tests (lokal, ohne Netz)
- [ ] Fixture-Helper: legt lokales Git-Repo in tmp_path an (git init, ZIP +
  .sha256 committen, Tag benchmark-set-v<N>)
- [ ] discover_sets parst ls-remote-Ausgabe (Tags), filtert fremde Tags,
  Cache (2. Aufruf kein 2. ls-remote)
- [ ] Install via git: clone, SHA aus Datei, aktiviert
- [ ] version-Auswahl: installiert genau diese Version
- [ ] Version ≤ aktuell → skip
- [ ] Pin-Pfad (url+sha wie 075) funktioniert weiterhin
- [ ] git nicht installiert / Fehler → last_error, kein Crash
- [ ] Frontend: Liste rendert, Install-Button je Release, Pinning-Hinweis
- [ ] Gates: tsc --noEmit, npm test, Backend-Suite GESAMT fail=0

## T6 — Beispiel-Repo + Doku
- [ ] `polyschnack-benchmark-data`: ZIP + .sha256 auf main committen,
  Tag benchmark-set-v1 setzen (Konvention erfüllt)
- [ ] README (GitHub): Repo-Konvention + git-URL-Konfiguration
- [ ] `docs/benchmark/admin.md`: git-basiert statt URL-Pinning dokumentieren
