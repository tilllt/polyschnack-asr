# Change 075: Benchmark-Sets selbstständig aus GitHub-Release installieren

## Problem

Neue Benchmark-Sets (z. B. das DEMAND-degradierte ASR-Testset v3) müssen
aktuell **manuell** auf der Box installiert werden:

1. Set lokal bauen (`prepare_cv_real.py` + `build_benchmark_pkg_v2.py`)
2. Als tar.gz auf Zipline hochladen
3. Auf der Box per `curl` + `sha256sum` + `tar` entpacken
4. Container-Neustart

Das ist fehleranfällig (Beispiel 2026-08-21: leere `latest.json` überschrieb
submittete Ergebnisse) und bei jedem neuen Set unnötig aufwändig. Das
**VAD-Paket macht es bereits richtig**: die Webapp lädt das offizielle
Testset-Artefakt selbst von GitHub (`VAD_PACKAGE_URL`, SHA256-verifiziert,
Change 062/065) — nur das ASR-Set fehlt.

## Ziel

Die Webapp kann sich neue Benchmark-Sets **selbst von GitHub-Releases**
holen: Admin klickt „Neues Set installieren" (oder Start-Trigger), die
App lädt das Release-ZIP, verifiziert die SHA256, entpackt nach
`versions/v{N}/`, aktiviert die neue Version. Kein SSH/tar/curl mehr.

## Design

### Release-Artefakt (GitHub-Release-Asset, deterministisch gebaut)

```
benchmark-set-<version>.zip
├── manifest.json        # {version, created_at, created_by, supersedes,
│                        #  methodology, disclaimer, axes, categories, samples[]}
├── audio/<sid>.wav      # 16 kHz mono, unkomprimiert (Benchmark-Lauf)
└── preview/<sid>.mp3    # 128 kbps (Anhören in der GUI)
```

- Version = `manifest.version` (Integer, aufsteigend; `supersedes` = vorige)
- Konvention identisch zu `versions/v{N}/` im `BENCHMARK_DATA_DIR`
- Release-Tag `benchmark-set-v<N>`, Asset-Name `benchmark-set-v<N>.zip`

### Konfiguration (env, wie VAD_PACKAGE_URL)

```yaml
BENCHMARK_SET_URL: "https://github.com/tilllt/polyschnack-benchmark-data/releases/download/benchmark-set-v3/benchmark-set-v3.zip"
BENCHMARK_SET_SHA256: "…"   # leer = nur Anzeige, kein Auto-Install
BENCHMARK_SET_AUTO_INSTALL: "false"  # true → beim Start prüfen/installieren
```

Ohne gesetzte URL: Mechanismus inaktiv (Status „nicht konfiguriert"),
bestehendes manuelles Deploy funktioniert unverändert.

### Backend

- `install_set_from_release(url, expected_sha)` in `benchmark_service.py`:
  1. Release-ZIP herunterladen (timeout 300 s)
  2. SHA256 des Bytes prüfen — Mismatch → RuntimeError (kein stilles Paket)
  3. `manifest.json` lesen → `version`, `supersedes`
  4. Ist `version` ≤ aktuelle → skip („bereits installiert")
  5. Entpacken nach `versions/v{N}/` (atomar: erst tmp-Verzeichnis,
     dann rename — nie halb installiert)
  6. Audio/Preview-Dateien vorhanden prüfen (Anzahl = samples)
  7. Ergebnis: {installed_version, sha256, sample_count, supersedes}
- `set_status()`: aktuelle Version, installierte Versionen, konfigurierte
  URL/SHA (SHA nur teilmaskiert), letzter Install-Fehler
- Router:
  - `GET /api/benchmark/sets` → Status (öffentlich lesbar, keine Secrets)
  - `POST /api/benchmark/sets/install` → Admin-Only, löst Install aus
- Beim Start: wenn `BENCHMARK_SET_AUTO_INSTALL=true` und URL gesetzt,
  einmalig prüfen/installieren (log, kein Crash bei Fehler)

### Frontend

- Admin-Bereich (Benchmark-Seite, nur wenn `admin=true`):
  - Button „Neues Set installieren" + Status-Zeile
  - Anzeige: aktuelle Version, verfügbare URL, SHA-Präfix, letzter Fehler
  - Nach erfolgreichem Install: Seite neu laden (neue Version sichtbar)
- Nicht-Admin: keine UI-Änderung (Status-Endpoint bleibt öffentlich für
  Monitoring, zeigt aber keine Secrets)

### Sicherheit

- **SHA256-Pflicht**: ohne gesetzte SHA kein Auto-Install; manueller
  Install-Button erlaubt das Nachreichen der SHA im Dialog (Admin)
- Download nur von HTTPS (URL-Schema-Check)
- Kein Exec, kein Pfad-Traversal (Zip-Einträge auf `audio/`, `preview/`,
  `manifest.json` beschränkt; Namen sanitized)
- VAD-Paket bleibt unberührt (eigene Logik, Change 062/065)

## Nicht-Ziel (Scope-Grenze)

- Kein automatisches Pollen der GitHub-API nach neuen Releases (nur
  installieren, wenn URL/SHA konfiguriert und angefordert)
- Kein automatischer Benchmark-Neulauf nach Install (Submit bleibt
  manuell/CI — Anti-Gaming: wer misst, muss die Rows selbst liefern)
- Kein Löschen alter Versionen (Runs bleiben an ihren SHA gebunden)

## Betroffene Dateien

- `webapp/app/benchmark_service.py` (Installer + Status)
- `webapp/app/routers/benchmark.py` (2 Endpoints)
- `webapp/app/config.py` (3 env-Optionen)
- `webapp/frontend/src/components/BenchmarkPage.tsx` (Admin-UI)
- `webapp/frontend/src/benchmark.ts` (Typen)
- `webapp/tests/test_benchmark_router.py` (+ Tests)
- `webapp/frontend/src/components/BenchmarkPage.test.tsx` (+ Tests)
- `webapp/app/main.py` (Start-Trigger, optional)
- `docs/` (Konfiguration)

## Erfolgskriterien

- [ ] Installer lädt + verifiziert + entpackt + aktiviert eine neue Version
- [ ] SHA-Mismatch → Fehler, kein Zustand geändert
- [ ] Ältere/gleiche Version → „bereits installiert", kein Überschreiben
- [ ] Paket-Dateien zählen = manifest.samples (kein stilles Teilpaket)
- [ ] Admin-UI zeigt Status + installiert per Klick
- [ ] Ohne konfigurierte URL: alles unverändert funktionsfähig
- [ ] Tests: Backend-Suite fail=0, Frontend grün, tsc 0
