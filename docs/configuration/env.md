# Umgebungsvariablen

## ASR-Backend wählen

| Variable | Werte | Default |
|----------|-------|---------|
| `ASR_BACKEND` | `pk-python`, `pk-cpp`, `qwen3-asr`, `ark-asr`, `moonshine-de`, `canary-asr` | `pk-python` |
| `ASR_URL` | URL des ONNX-Dienstes | `http://asr:5092` |
| `POLYSCHNACK_DEFAULT_BACKEND` | wie `ASR_BACKEND` (Default für neue Jobs, per Admin-GUI änderbar) | `pk-python` |

## Webapp-Umgebungsvariablen

| Variable | Default | Beschreibung |
|----------|---------|-------------|
| `ASR_URL` | `http://asr:5092` | ASR-Service-URL |
| `ASR_BACKEND` | `pk-python` | Welcher Adapter |
| `VAD_TRIM_SILENCE` | `false` | Stille-Trimmung aktivieren |
| `DIAR_URL` | `http://diar:5096` | Diarization-Service (CrispASR-diar-Container) |
| `DIARIZE_METHOD` | `pyannote` | Diarization-Methode (`pyannote`\|`foxnose`\|`energy`\|…) — per GUI überschreibbar |
| `PUBLIC_RETENTION_MINUTES` | `60` | Auto-Löschung öffentl. Aufnahmen |
| `OIDC_CLIENT_ID` | `""` | OIDC-Client-ID (leer = kein Auth) |
| `OIDC_ISSUER` | `""` | OIDC-Issuer-URL |
| `SESSION_SECRET` | auto | Session-Key |
| `BASE_URL` | `http://localhost:8088` | Externe URL für OIDC-Redirects |
| `POLYSCHNACK_ADMINS` | `""` | Komma-Liste (OIDC-sub oder E-Mail) mit Admin-Rechten |
| `POLYSCHNACK_ADMIN_GROUPS` | `""` | Komma-Liste von OIDC-Gruppen mit Admin-Rechten |
| `DOCKER_PROXY_URL` | `http://docker-proxy:2375` | Restriktiver Docker-Socket-Proxy |
| `POLYSCHNACK_MAX_QUEUE_LEN` | `20` | Maximale Jobs in der Transcribe-Queue |

## Post-Processing & Delivery

| Variable | Default | Bedeutung |
|---|---|---|
| `POLYSCHNACK_PUNCTUATION_MODE` | `off` | `off` \| `local` \| `llm` |
| `POLYSCHNACK_DEFAULT_LLM_ENHANCE` | `false` | LLM-Optimierung default an |
| `POLYSCHNACK_LLM_URL` | *(leer)* | OpenAI-kompatibler Endpunkt (z. B. eigener LiteLLM-Proxy) |
| `POLYSCHNACK_LLM_API_KEY` | *(leer)* | API-Key für obigen Endpunkt |
| `POLYSCHNACK_LLM_MODEL` | `deepseek-chat` | Modellname |
| `POLYSCHNACK_SMTP_HOST` | *(leer)* | SMTP-Server (leer = Mail-Targets deaktiviert) |
| `POLYSCHNACK_SMTP_PORT` | `587` | SMTP-Port |
| `POLYSCHNACK_SMTP_USER` / `_PASS` | *(leer)* | SMTP-Login |
| `POLYSCHNACK_SMTP_FROM` | *(leer)* | Absender-Adresse |

## Benchmark

| Variable | Default | Bedeutung |
|----------|---------|-----------|
| `BENCHMARK_DATA_DIR` | `/data/benchmark` | Volume für versionierte Manifeste + Audio + Ergebnisse |
