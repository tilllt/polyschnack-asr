# Benchmark

Öffentliche Seite unter **`https://<webapp>/benchmark`** (Pfad unter der
Webapp, keine Subdomain) — Methodik, hörbare Samples, Ergebnisse und
Preisvergleich.

## Für normale User (kein Login nötig)

- **Methodik-Karte** — Version, Stand, Kategorien, Anti-Gaming-Hinweis
- **Test-Set · 2-Achsen-Matrix** — Kanal × Inhalt als 8×8-Matrix mit
  Sample-Zählung; Klick auf eine Zelle **filtert die Samples** darunter
- **„Wie ist das Test-Set aufgebaut?"** — verständliche Erklärung der
  Taxonomie (Best Practice aus GigaSpeechBench/LibriSpeech/REVERB/CHiME)
- **Samples nach Kategorie** (collapsible, nur eine offen):
  - **Preview** (MP3 128 kbps, WaveSurfer-Player) + **finale WAV** (unkomprimiert, Download)
  - Referenztext ein-/ausblendbar
- **Ergebnisse** — gepoolte Benchmark-Ergebnisse (`results/latest.json`)
- **Preisvergleich** — WER/€-Matrix (Selbstkosten vs. SaaS vs. kommerziell)

Bearbeiten ist **nicht** möglich — Read-only für normale User.

## Datenlayout (`benchmark_data`)

```
benchmark_data/
  versions/v1/manifest.json   # Samples + Kategorien (immutable pro Version)
  versions/v1/audio/*.wav     # finale WAV (unkomprimiert)
  versions/v1/preview/*.mp3   # MP3 128k (on-demand via ffmpeg)
  results/latest.json         # gepoolte Ergebnisse
  pricing.json                # Preisvergleich (Selbstkosten × markup_x)
```

`BENCHMARK_DATA_DIR` (Default: `/data/benchmark`) zeigt auf das Volume.
Seed: `webapp/benchmark/seed_benchmark_data.py` (manuell, nie in CI).

## Seed vor dem ersten Start (wichtig!)

Die Benchmark-Seite zeigt **ohne Seed-Daten nichts** („Benchmark-Daten sind
noch nicht verfügbar"). Vor dem ersten Start das Volume befüllen — die
Selektions-/Audio-Dateien kommen aus dem separaten polyschnack-benchmark-Repo:

```bash
cd webapp
SELECTION=/pfad/zum/polyschnack-benchmark/benchmark/selection/cv_selection_v1.json \
TTS_SELECTION=/pfad/zum/polyschnack-benchmark/benchmark/selection/tts_selection.json \
CV_WAV_DIR=/pfad/zum/polyschnack-benchmark/benchmark/data/cv \
TTS_WAV_DIR=/pfad/zum/polyschnack-benchmark/benchmark/data/tts \
TAXONOMY=/pfad/zum/polyschnack-benchmark/benchmark/spec/taxonomy.json \
BENCHMARK_DATA_DIR=<host-mount>/benchmark \
.venv/bin/python benchmark/seed_benchmark_data.py
```

- `BENCHMARK_DATA_DIR` muss auf den **Host-Pfad des Volumes** zeigen
  (compose: `./DATA/poc-data:/data` → `DATA/poc-data/benchmark`).
- Der Seed kopiert die WAVs (unkomprimiert) und erzeugt die MP3-128k-Previews
  per ffmpeg.

API: `GET /api/benchmark/meta`, `/samples`, `/audio/{id}`, `/preview/{id}`,
`/results`, `/pricing`, `/versions` — POST `/reject`, `/edit` (Admin only).

## Benchmark-Container (periodisch per Cron)

Der Benchmark läuft **nicht** als dauerhafter Service, sondern als
**Einmal-Container**, der per Host-Cron periodisch gestartet wird:

```bash
# Einmal manuell:
docker compose -f compose.yml -f compose.benchmark.yml run --rm benchmark

# Periodisch (Host-Crontab, z. B. täglich 04:00):
0 4 * * * cd /pfad/zum/polyschnack-checkout && docker compose -f compose.yml -f compose.benchmark.yml run --rm benchmark >> /var/log/polyschnack-benchmark.log 2>&1
```

Der Container liest `versions/vN/manifest.json` (aktive Samples), schickt
sie an die Backends (Compose-Netzwerk) und schreibt `latest.json` +
`pricing.json` ins Volume — die Webapp zeigt sie ohne Neustart an.

- **Volumes (Least-Privilege):** `/data` ro, nur `/data/benchmark` rw
- **CPU-only**, endet nach dem Lauf (kein Leerlauf-Verbrauch)
- **Konfig:** `BENCH_BACKENDS` (Komma-Liste) + `BENCH_BACKEND_URLS` (JSON-Map)
- **Image:** CI-Job `build-benchmark` → Harbor (braucht `CONFIG_JSON`-Variable)

## Wichtig vor dem Deployment

Die Benchmark-Seite zeigt **ohne Seed-Daten nichts** („Benchmark-Daten sind
noch nicht verfügbar"). Vor dem ersten Start das Volume befüllen:

```bash
cd webapp
SELECTION=/pfad/zum/polyschnack-benchmark/benchmark/selection/cv_selection_v1.json \
TTS_SELECTION=/pfad/zum/polyschnack-benchmark/benchmark/selection/tts_selection.json \
CV_WAV_DIR=/pfad/zum/polyschnack-benchmark/benchmark/data/cv \
TTS_WAV_DIR=/pfad/zum/polyschnack-benchmark/benchmark/data/tts \
TAXONOMY=/pfad/zum/polyschnack-benchmark/benchmark/spec/taxonomy.json \
BENCHMARK_DATA_DIR=<host-mount>/benchmark \
.venv/bin/python benchmark/seed_benchmark_data.py
```

- `BENCHMARK_DATA_DIR` muss auf den **Host-Pfad des Volumes** zeigen
  (compose: `./DATA/poc-data:/data` → `DATA/poc-data/benchmark`).
- Der Seed kopiert die WAVs (unkomprimiert) und erzeugt die MP3-128k-Previews
  per ffmpeg.

→ Weiter: [2-Achsen-Taxonomie](taxonomy.md) · [Admin-Workflow](admin.md)
