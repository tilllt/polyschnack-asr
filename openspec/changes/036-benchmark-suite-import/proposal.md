# Change 036: Hash-gesicherter Benchmark-Suite-Import (Backends + Versions-Upload)

**Status:** in Arbeit · **Datum:** 2026-08-20

## Problem

1. Die deployte Polyschnack-Instanz (whisper.cia-spandau.de) zeigt unter `/benchmark`
   die **alte Benchmark-Grundlage** (Version 1, 210 Samples, erzeugt 19.08. 12:59).
   Die aktuelle 207er-Suite (`polyschnack-benchmark/benchmark/data/manifest.json`,
   207 Samples) wurde von allen vast-Läufen (ps-pk-onnx, crispr-pk-cpp, moonshine-de,
   canary, qwen3, whisper-large-v3, voxtral-mini-realtime) als Grundlage verwendet —
   ist aber **nicht auf der Box**.
2. Die Suite-Backends `whisper-large-v3` (faster-whisper large-v3) und
   `voxtral-mini-realtime` (vLLM Mistral Voxtral-Mini-4B-Realtime-2602) sind in
   `backends.yaml` **nicht registriert** → `POST /api/benchmark/submit` lehnt die
   Läufe mit `unknown backend` ab (die Box-Backends `crispr-whisper`/`crispr-voxtral`
   sind CrispASR-GGUF-Varianten, NICHT dieselben Implementierungen).
3. Ohne Hash-Gate können Results auf falsche Grundlagen geschrieben werden
   (`apply_submission` erzwingt zwar `manifest_version`+`manifest_sha256`, aber nur,
   wenn der Submitter die SHA der IST-Grundlage kennt).

## Entscheidung

- **Hash-gesicherter Versions-Upload:** Die 207er-Suite wird als **neue Version**
  (vN+1, `supersedes` = aktive IST-Version) ins `benchmark_data`-Volume der Box
  eingespielt — nie die bestehende Version überschreiben (Immutable-Prinzip).
  `package_sha256` (= sha256(manifest.json) + sha256(je WAV, sortiert) →
  sha256(Konkatenation)) wird **deterministisch im Skript berechnet** und als Gate
  verwendet: IST-SHA (Box-Volume) vs. NEU-SHA (Paket) → nur einspielen, wenn
  verschieden; Submit nur mit der SHA der **danach aktiven** Version.
- **Suite-Backends registrieren:** `whisper-large-v3` + `voxtral-mini-realtime`
  als Remote-Backends (OpenAI-kompatibel, `type: remote`, `base_url` per Env
  `<ID>_URL`, model aus Change 027). `get_service()` prüft nur die Existenz —
  damit akzeptiert `/submit` die Läufe; die GUI zeigt sie ehrlich als offline
  (laufen on-demand auf vast).
- **Import über den offiziellen Submit-Weg:** Results werden als
  `result_benchmark_*.json` → `rows[]` (sample_id/wer/rtf) konvertiert, HMAC-SHA256
  signiert (`X-Benchmark-Signature`, Bearer Shared-Key aus `BENCHMARK_API_KEYS`)
  und per `POST /api/benchmark/submit` gepoolt (inkl. `per_category`, Change 032).
  Kein direktes Editieren von `latest.json`.

## Tasks

- [x] Suite-Backends in `webapp/app/backends.yaml` registrieren (whisper-large-v3, voxtral-mini-realtime)
- [x] `BENCHMARK_API_KEYS` in compose.yml für ps-webapp verdrahten (Change-031-Lücke: Env fehlte → Endpunkte 503)
- [x] Build-Skript: 207er-Suite → `benchmark_data`-Version + `package_sha256` + Tarball (deterministisch)
- [x] Box-Import-Skript: Hash-Gate, Versions-Einspielen, Backend-Registrierung, Submit, Verifikation
- [x] Paket + Result-JSONs bereitstellen (Zipline) und Anleitung an User

## Anhang: Benchmark-Key (Shared-Key, Change 031)

Die Endpunkte `GET /api/benchmark/package`, `/package/sha256` und
`POST /api/benchmark/submit` sind mit einem Shared-Key geschützt
(`Authorization: Bearer <key>` + HMAC-SHA256-Signatur im Header
`X-Benchmark-Signature` über den rohen Request-Body, hex).

**Key erzeugen:**
```bash
openssl rand -hex 32
```

**Aktivieren (auf der Box):**
1. In die `.env` des Checkouts eintragen (mehrere Keys kommasepariert):
   ```
   BENCHMARK_API_KEYS=<key1>,<key2>
   ```
2. Webapp neu starten (Compose reicht die Variable seit Change 036 durch):
   ```bash
   ./polyschnack-manage.sh deploy
   # bzw. docker compose up -d ps-webapp
   ```
3. Prüfen: `curl -s -o /dev/null -w "%{http_code}" https://<host>/api/benchmark/meta`
   → 200; die Submit-Endpunkte antworten ohne Key mit 401/503, mit Key + Signatur 200.

**Im Import-Skript:** `--key <key>` oder automatisch aus `BENCHMARK_API_KEYS`
in der `.env` (erste Key).
