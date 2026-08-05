# Quickstart

**Voraussetzung:** Docker mit Compose v2. Für GPU zusätzlich das NVIDIA
Container Toolkit.

PolySchnack ist **hybrid**: Der Default-Stack läuft überall (CPU), mit einem
Overlay wird GPU-Zugriff aktiviert (ASR + Diarization).

```bash
git clone <dein-repo-url>
cd polyschnack

# Variante A — CPU (läuft überall, kein NVIDIA-Toolkit nötig):
docker compose up -d

# Variante B — GPU (RTX 3090 o.ä., NVIDIA Container Toolkit installiert):
docker compose -f compose.yml -f compose.gpu.yml up -d
```

- **Web UI:** http://localhost:8088
- **ASR API (direkt):** http://localhost:5092

## Optional: Login + Admin-Bereich (OIDC)

Über das Dummy-Overlay:

```bash
docker compose -f compose.yml -f compose.oidc.yml up -d   # Werte ersetzen!
```

Alle Werte in `compose.oidc.yml` sind Platzhalter — vor Produktion
`OIDC_CLIENT_ID/SECRET`, `OIDC_ISSUER`, `SESSION_SECRET`, `BASE_URL` und
`POLYSCHNACK_ADMINS` ersetzen. Details: [OIDC-Auth](configuration/oidc.md).

## Optional: Weitere Backends

```bash
# Container erzeugen (GUI startet sie on demand):
docker compose -f compose.yml -f compose.backends.yml \
  --profile cpp --profile qwen3 --profile ark up -d --no-start

# Oder ein Backend direkt mitstarten:
docker compose -f compose.yml -f compose.backends.yml --profile cpp up -d
```

Die Modelle müssen einmalig geladen werden — siehe
[Modelle laden](backends/models.md).

## Wie Hybrid funktioniert (Weg 1)

Jeder Service ist **EIN Image für GPU UND CPU** — die CUDA/ggml-Binaries
enthalten den CPU-Backend und wählen automatisch
(`ggml_backend_init_best` = CUDA > Metal > Vulkan > CPU; approach-a nutzt
`POLYSCHNACK_USE_GPU=auto` mit onnxruntime-gpu). Mit GPU-Zugriff (Overlay
`compose.gpu.yml` → `runtime: nvidia`) läuft alles auf der GPU, ohne Overlay
automatisch auf der CPU.

Die **Diarization** läuft im eigenen CrispASR-diar-Container (`diar`,
Port 5098) — ebenfalls hybrid. Die Webapp selbst ist **CPU-only** (kein
torch/pyannote im Image, ~2,5–3 GB schlanker).
