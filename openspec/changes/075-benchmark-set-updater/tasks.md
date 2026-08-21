# Tasks — Change 075: Benchmark-Sets selbstständig installieren

## T0 — Konfiguration (config.py)
- [ ] `BENCHMARK_SET_URL`, `BENCHMARK_SET_SHA256`, `BENCHMARK_SET_AUTO_INSTALL`
  als Settings ergänzen (Default leer/false; kein Verhalten ohne URL)

## T1 — Backend-Installer (benchmark_service.py)
- [ ] `install_set_from_release(url, expected_sha)`:
  HTTPS-Check → Download (timeout 300) → SHA256-Verifikation (Mismatch =
  RuntimeError, kein Zustand geändert) → manifest.json lesen
- [ ] Version ≤ aktuell → `{"skipped": True, "reason": "bereits installiert"}`
- [ ] Zip sicher entpacken: nur `manifest.json`, `audio/*.wav`, `preview/*.mp3`;
  Namen sanitized (kein Traversal); erst nach `versions/.tmp-v{N}`, dann
  atomic rename nach `versions/v{N}`
- [ ] Vollständigkeitsprüfung: Anzahl audio/preview == samples im Manifest
- [ ] `set_status()`: {current_version, installed_versions[], configured_url,
  sha_prefix, auto_install, last_error}
- [ ] `supersedes` im neuen Manifest setzen = alte aktuelle Version (falls
  fehlt, beim Install ergänzen)

## T2 — Router (routers/benchmark.py)
- [ ] `GET /api/benchmark/sets` → Status (keine Secrets: SHA nur 8-Char-Präfix)
- [ ] `POST /api/benchmark/sets/install` → Admin-Only (bestehender
  Admin-Check des Routers), Body optional {url, sha256} als Override;
  Response {ok, installed_version, sha256, sample_count} oder {ok:false, reason}

## T3 — Start-Trigger (main.py / Startup-Hook)
- [ ] Wenn AUTO_INSTALL=true + URL gesetzt: einmalig prüfen/installieren,
  Fehler nur loggen (kein Crash der App)

## T4 — Frontend
- [ ] `benchmark.ts`: Typen `BenchmarkSetStatus`, `SetInstallResponse`
- [ ] `BenchmarkPage.tsx`: wenn `admin` — Sektion „Benchmark-Sets":
  Status-Zeile (aktuelle Version, Quelle, SHA-Präfix, letzter Fehler) +
  Button „Neues Set installieren" (bei Fehlern: Meldung sichtbar, kein
  stiller Fehler)
- [ ] Nach Erfolg: `onReload()` + Status neu laden

## T5 — Tests
- [ ] Backend: Installer happy path (tmp-Dir-Fixture mit Manifest+WAVs),
  SHA-Mismatch (nichts geändert), Version ≤ aktuell (skip), Traversal-Zip
  (abgelehnt), unvollständiges Paket (Fehler)
- [ ] Router: GET sets (Statusform, kein voller SHA), POST install ohne
  Admin → 403, mit Admin → install
- [ ] Frontend: Status-Anzeige rendert, Install-Button ruft API, Fehler
  sichtbar
- [ ] Gates: tsc --noEmit, npm test, Backend-Vollsuite GESAMT fail=0

## T6 — Release-Doku + Beispiel
- [ ] `docs/benchmark/` Notiz: Release-Artefakt-Format (ZIP-Struktur, Tag-
  Konvention `benchmark-set-v<N>`) + Konfiguration (3 env-Optionen)
- [ ] Beispieldaten: lokales Set-Paket als ZIP gebaut (aus vorhandenem
  `benchmark_data_pkg`) → Installer-Test dagegen (lokale Datei-URL)
