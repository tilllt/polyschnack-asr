# Quickstart

**Voraussetzung:** Docker mit Compose v2. Für GPU zusätzlich das NVIDIA
Container Toolkit (siehe Repo-`README.md`, Abschnitt Minimum Requirements).

## Variante C (empfohlen): `polyschnack-manage.sh`

Die „Fernbedienung" für den kompletten Stack — erkennt GPU automatisch,
aktiviert OIDC nur mit echten Credentials und provisioniert alle Backends
(Start on demand über die Admin-GUI):

```bash
git clone <dein-repo-url> && cd polyschnack
./polyschnack-manage.sh            # = start
./polyschnack-manage.sh status     # läuft alles? GPU? Welche Backends?
./polyschnack-manage.sh models     # fehlende GGUF-Modelle der AKTIVEN Backends laden
./polyschnack-manage.sh update     # kompletter Deploy: git pull + pull + models + start
```

**Alle Befehle:**

| Befehl | Funktion |
|---|---|
| `pull` | Zieht ALLE Images (Kern + optionale Backends inkl. Profile) |
| `start` | Startet Kern-Stack (docker-proxy, ps-pk-onnx, crispr-diar, crispr-align, ps-webapp), provisioniert Backends mit `--no-start` |
| `stop` / `restart` / `down` | Stoppt / Neustart / entfernt Container (Volumes bleiben) |
| `status` | Zustand aller Services + GPU-Erkennung + aktive Backend-Auswahl |
| `logs [SVC]` | Folgt den Logs (alle oder ein Service) |
| `models` | Lädt fehlende GGUF-Modelle der aktiven Backends nach `./DATA/models` (idempotent) |
| `benchmark` | Startet den Benchmark-Einmal-Container (Konfiguration via `BENCH_BACKENDS`, `BENCH_BACKEND_URLS`, `OPENAI_API_KEY` in `.env`) |
| `key` | Zeigt Benchmark-Key-Sichtbarkeit maskiert (Diagnose bei 503/401) |
| `update` | `git pull` → `pull` → `models` → `start` |
| `selfupdate` | Aktualisiert Skript **und** `backends.yaml` (public GitHub-Mirror) |
| `help` | Befehlshilfe |

!!! tip "Nach dem Aktivieren eines Backends"
    Immer einmal `./polyschnack-manage.sh models` (oder `update`) ausführen —
    die GGUFs liegen nicht im Image, sondern in `./DATA/models`. Häufigster
    Grund für „Backend startet nicht".

## Variante A/B (manuell, ohne Manage-Skript)

```bash
git clone <dein-repo-url> && cd polyschnack

# Variante A — CPU (läuft überall):
docker compose up -d

# Variante B — GPU (NVIDIA Container Toolkit nötig):
docker compose -f compose.yml -f compose.backends.yml -f compose.gpu.yml up -d
```

- **Web UI:** http://localhost:8088
- **ASR API (direkt):** http://localhost:5092/v1

### Optional: weitere Backends

```bash
# Container erzeugen (GUI startet sie on demand):
docker compose -f compose.yml -f compose.backends.yml \
  --profile crispr-pk-cpp --profile crispr-qwen3 --profile crispr-ark up -d --no-start

# Oder ein Backend direkt mitstarten:
docker compose -f compose.yml -f compose.backends.yml --profile crispr-pk-cpp up -d
```

Modelle einmalig laden — siehe [Modelle laden](backends/models.md).

### Optional: Login + Admin (OIDC)

```bash
# Werte in die .env schreiben (Repo-Root) — das Overlay interpoliert sie:
#   OIDC_CLIENT_ID / OIDC_CLIENT_SECRET / OIDC_ISSUER / SESSION_SECRET /
#   BASE_URL / POLYSCHNACK_ADMINS (sub ODER email, kommagetrennt)
docker compose -f compose.yml -f compose.oidc.yml up -d
```

Die Defaults im Overlay sind DUMMY-Werte — echte Werte gehören in die `.env`.
Details: [OIDC-Auth](configuration/oidc.md).

## Backends aktivieren/deaktivieren

Die aktive Auswahl steuert `POLYSCHNACK_BACKENDS` in der `.env` (Space-getrennt,
Katalog-Namen aus `backends.yaml`, z. B. `crispr-qwen3`; alte Kurznamen
`pk-cpp qwen3 ark moonshine-de canary` funktionieren als Alias):

```bash
# .env neben polyschnack-manage.sh
POLYSCHNACK_BACKENDS="crispr-qwen3 crispr-ark"
```

Nur aktive Backends werden provisioniert und ihre Modelle geladen.
Details: [Compose-Referenz](compose.md).

## Deployment auf einem Server ohne Git-Checkout (z. B. ki-box)

Der Server braucht kein Git-Repository — die Dateien kommen per Download:

```bash
cd /opt/container/polyschnack          # dein Installations-Ordner
for f in compose.yml compose.backends.yml compose.gpu.yml polyschnack-manage.sh; do
  curl -fsSL -o "$f" "https://raw.githubusercontent.com/tilllt/polyschnack-asr/main/$f"
done
chmod +x polyschnack-manage.sh
mkdir -p webapp/app
curl -fsSL -o webapp/app/backends.yaml \
  https://raw.githubusercontent.com/tilllt/polyschnack-asr/main/webapp/app/backends.yaml
./polyschnack-manage.sh update
```

!!! warning "compose.oidc.yml niemals überschreiben"
    Dort stehen die echten Login-Zugangsdaten. Sie gehört nicht ins
    öffentliche Repo und wird vom Download-Befehl bewusst ausgelassen.

Danach hält `selfupdate` Skript **und** `backends.yaml` aktuell; `update`
zieht Images, Modelle und startet. Die übrigen compose-Dateien bei größeren
Releases einmal per Download-Befehl nachziehen.

## Wie Hybrid funktioniert

Jeder Service ist **EIN Image für GPU UND CPU** — die CUDA/ggml-Binaries
enthalten den CPU-Backend und wählen automatisch (`ggml_backend_init_best` =
CUDA > Metal > Vulkan > CPU; approach-a nutzt `POLYSCHNACK_USE_GPU=auto` mit
onnxruntime-gpu). Mit GPU-Zugriff (Overlay `compose.gpu.yml` →
`runtime: nvidia`) läuft alles auf der GPU, ohne Overlay automatisch auf der
CPU. Die Webapp selbst ist **CPU-only** (kein torch/pyannote im Image,
~2,5–3 GB schlanker).
