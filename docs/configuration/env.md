# Umgebungsvariablen

## ASR-Backend wählen

| Variable | Werte | Default |
|----------|-------|---------|
| `ASR_BACKEND` | `ps-pk-onnx`, `crispr-pk-cpp`, `crispr-qwen3`, `crispr-ark`, `crispr-moonshine-de`, `crispr-canary` | `ps-pk-onnx` |
| `ASR_URL` | URL des ONNX-Dienstes | `http://ps-pk-onnx:5092` |
| `POLYSCHNACK_DEFAULT_BACKEND` | wie `ASR_BACKEND` (Default für neue Jobs, per Admin-GUI änderbar) | `ps-pk-onnx` |

## Webapp-Umgebungsvariablen

| Variable | Default | Beschreibung |
|----------|---------|-------------|
| `ASR_URL` | `http://ps-pk-onnx:5092` | ASR-Service-URL |
| `ASR_BACKEND` | `ps-pk-onnx` | Welcher Adapter |
| `VAD_TRIM_SILENCE` | `false` | Stille-Trimmung aktivieren |
| `DIAR_URL` | `http://crispr-diar:5098` | Diarization-Service (CrispASR-diar-Container) |
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
| `POLYSCHNACK_ALIGN_WORDS` | `true` | Word-Alignment nach der ASR (Forced Aligner) aktiv/deaktiviert |
| `POLYSCHNACK_DEFAULT_PUNCTUATION` | `false` | Satzzeichen-Toggle default an |
| `WEBAPP_PORT` | `8088` | Host-Port der Web-UI (Compose-Ebene, `.env`; Container-Port innen bleibt 8088) |

## Anonyme Nutzer (Limits)

| Variable | Default | Beschreibung |
|----------|---------|-------------|
| `PUBLIC_RETENTION_MINUTES` | `60` | Auto-Löschung öffentlicher Aufnahmen (Shared Space ohne Login) |
| `POLYSCHNACK_ANON_RETENTION_MINUTES` | `15` | Gültigkeit von Anon-Share-Links |
| `POLYSCHNACK_ANON_MAX_DURATION_S` | `300` | Max. Audiodauer für anonyme Nutzer |
| `POLYSCHNACK_ANON_MAX_UPLOAD_MB` | `100` | Max. Uploadgröße für anonyme Nutzer |
| `POLYSCHNACK_ANON_MAX_DISK_MB` | `500` | Max. Gesamtspeicher aller anonymen Aufnahmen |
| `MAX_UPLOAD_SIZE_MB` | `1024` | Max. Uploadgröße allgemein |

## Tor-Fallback (YouTube-Import, Change 043)

| Variable | Default | Beschreibung |
|----------|---------|-------------|
| `POLYSCHNACK_TOR_FALLBACK` | `false` | `on` = YouTube-Downloads dürfen bei Bot-Erkennung über den Tor-Sidecar laufen |
| `POLYSCHNACK_TOR_MAX_CIRCUITS` | `5` | Max. parallele Tor-Circuits |
| `POLYSCHNACK_TOR_MAX_SIZE_MB` | `500` | Max. Dateigröße für Tor-Downloads |
| `POLYSCHNACK_TOR_MAX_PER_HOUR` | `2` | Max. Tor-Downloads pro Stunde |
| `POLYSCHNACK_TOR_IDLE_MINUTES` | `30` | Tor-Sidecar nach Leerlauf stoppen |

## Benchmark

| Variable | Default | Bedeutung |
|----------|---------|-----------|
| `BENCHMARK_DATA_DIR` | `/data/benchmark` | Volume für versionierte Manifeste + Audio + Ergebnisse |
| `BENCH_BACKENDS` | alle lokalen | Welche Backends der Benchmark misst |
| `BENCH_BACKEND_URLS` | JSON-Map | URL-Overrides (auch externe OpenAI-kompatible Endpunkte) |
| `OPENAI_API_KEY` / `LITELLM_API_KEY` | — | Keys für externe Endpunkte |

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
