# Change 076: Benchmark-Set-Discovery — git-basiert, host-agnostisch

## Problem

Change 075 hat den Install-Mechanismus gebaut, aber die Quelle ist eine
**env-hardcodierte URL** (`BENCHMARK_SET_URL` + `BENCHMARK_SET_SHA256`).
Damit ist der GUI-Button nur ein einmaliger Klick auf das eine fixe Paket:

- Neues Set v2 → compose.yml editieren, Container neu starten — genau das
  manuelle Umständliche, das der Auto-Update beseitigen sollte.
- Die Webapp „weiß" nicht, dass es ein neueres Release gibt.

Zusätzliche Anforderung (User, 2026-08-21): **kein GitHub-Hardcode** — die
Quelle muss austauschbar sein. „Ein git ist ok, aber nicht GitHub."
Der Mechanismus darf keine GitHub-spezifische API voraussetzen.

## Ziel

Die Webapp **findet neue Benchmark-Sets selbst über Git** — host-agnostisch:
`git ls-remote --tags` listet die verfügbaren Set-Versionen eines
beliebigen Git-Repos (GitHub, GitLab, selbst gehostet, lokal), `git clone
--depth 1 --branch benchmark-set-v<N>` lädt genau die gewählte Version.
Env braucht nur noch die **Git-URL** (einmalig). SHA-Verifikation über die
`.sha256`-Datei, die im Repo neben dem ZIP liegt.

## Design

### Repo-Konvention (jedes Git-Repo, jeder Host)

```
benchmark-set-v<N>.zip            # das Set (manifest.json + audio/ + preview/)
benchmark-set-v<N>.zip.sha256     # SHA256 als Textdatei (sha256sum-Format)
```

- Tag `benchmark-set-v<N>` markiert die Version (für `--branch`-Clone)
- Kein GitHub-API-Aufruf, keine Host-spezifische Logik — nur git

### Konfiguration (env)

```yaml
BENCHMARK_SET_GIT_URL: "https://github.com/tilllt/polyschnack-benchmark-data.git"
# beliebiger Host: https://gitlab.rand0m.me/... .git, ssh://..., lokaler Pfad
BENCHMARK_SET_AUTO_INSTALL: "false"   # optional: beim Start prüfen/installieren
# optional weiterhin wirksam (Fallback/Pinning, Change 075):
BENCHMARK_SET_URL: ""      # wenn gesetzt: direkter HTTPS-Install (kein git)
BENCHMARK_SET_SHA256: ""   # wenn gesetzt: zusätzliche Verifikation/Pin
```

Priorität beim Install:
1. Explizite `url` im Request (Admin-Override) → Change 075 (Pin)
2. `BENCHMARK_SET_URL` env (Pinning-Fallback) → Change 075
3. Sonst: **git-basiert** über `BENCHMARK_SET_GIT_URL` → gewählte/neueste
   Release-Version

### Backend (benchmark_service.py)

- `discover_sets(git_url)` → `git ls-remote --tags <url>` (subprocess,
  timeout 60 s, `GIT_TERMINAL_PROMPT=0`), filtert Tags `benchmark-set-v<N>`,
  liefert je Version: `{version, tag}`. Cache 300 s (ls-remote ist billig,
  aber Rate-Limits an manchen Hosts).
  - Fehler (git nicht installiert, Netz, Auth) → RuntimeError, kein Crash
- `install_set_from_release(url=None, expected_sha=None, git_url=None, version=None)`:
  - url/expected_sha wie gehabt (Pin-Pfad, Change 075)
  - sonst: `git clone --depth 1 --branch benchmark-set-v<N> --single-branch
    <git_url> <tmpdir>` → ZIP + SHA-Datei aus dem Checkout lesen →
    SHA-Verifikation → gleicher Ablauf wie 075 (sicheres Entpacken,
    Vollständigkeit, atomic rename)
  - `git_url`-Arg oder env; ohne Version → neueste aus ls-remote
- `_parse_sha_asset` bleibt (sha256sum-Format)
- `set_status()` erweitert: `git_url`, `available` (aus discover_sets,
  gecacht), `pinning_mode` (true wenn BENCHMARK_SET_URL gesetzt)

### Sicherheit

- Git-URL: https://, ssh:// oder lokaler Pfad (Admin-konfiguriert);
  `GIT_TERMINAL_PROMPT=0` (kein interaktives Credential-Hängen)
- Timeouts: ls-remote 60 s, clone 300 s
- SHA-Pflicht: aus `.sha256`-Datei im Checkout (oder env-SHA); Mismatch →
  Abbruch, kein Zustand geändert
- Traversal-Schutz, Vollständigkeitsprüfung, atomic rename — unverändert
- Kein Ausführen von Repo-Code: nur Dateien ZIP/SHA lesen

## Nicht-Ziel

- Kein automatisches Polling/Install ohne Admin-Aktion (außer AUTO_INSTALL)
- Kein automatisierter Benchmark-Neulauf nach Install
- Kein Löschen alter Versionen
- Kein GitHub-API-Code (bewusst entfernt — kein `api.github.com`)

## Betroffene Dateien

- `webapp/app/benchmark_service.py` (discover_sets git, Installer-Erweiterung)
- `webapp/app/routers/benchmark.py` (Body: git_url statt repo)
- `webapp/app/config.py` (BENCHMARK_SET_GIT_URL)
- `webapp/frontend/src/benchmark.ts` (Typen)
- `webapp/frontend/src/components/BenchmarkPage.tsx` (Status + verfügbare Sets)
- `webapp/tests/test_benchmark_router.py` (git-Fixture-Tests, lokal ohne Netz)
- `webapp/frontend/src/components/BenchmarkPage.test.tsx`
- `docs/benchmark/admin.md`

## Erfolgskriterien

- [x] Discovery via `git ls-remote --tags` (kein GitHub-API-Call im Code)
- [x] Install ohne env-URL: clone des Tags, SHA aus `.sha256`, aktivieren
- [x] `version`-Auswahl installiert genau diese Version
- [x] Version ≤ aktuell → skip (nie überschreiben)
- [x] env-URL/SHA-Pin (Change 075) funktioniert weiterhin
- [x] GUI zeigt verfügbare Sets + installiert per Klick; Fehler sichtbar
- [x] Tests laufen gegen **lokale Git-Fixtures** (tmp_path, kein Netz)
- [x] Backend-Suite fail=0, Frontend grün, tsc 0

## Fix 2026-08-21 (CI 4290): git fehlt in CI-Image + Produktions-Dockerfile

Die lokale Vollsuite lief grün, aber die GitLab-Pipeline schlug fehl:
`FileNotFoundError: [Errno 2] No such file or directory: 'git'` in den
4 Discovery-Tests (`test_discover_sets_parses_tags`, `_cached`,
`test_install_via_git_uses_sha_file`, `test_install_git_version_choice`).
`python:3.13-slim` hat kein git.

Zwei Stellen gefixt:
- `.gitlab-ci.yml` `test-webapp`: `apt-get install ... ffmpeg git`
- `webapp/Dockerfile`: `apt-get install ... ffmpeg nodejs git` — die
  Webapp führt `git ls-remote`/`git clone` zur LAUFZEIT aus, das
  Produktions-Image braucht git ebenfalls (nicht nur der CI-Container).

Commit: Teil von 077 (17c645f, CI-Run 4292).
