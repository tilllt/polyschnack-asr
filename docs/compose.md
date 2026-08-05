# Compose-Referenz

Der Stack ist bewusst in **fünf Compose-Dateien** aufgeteilt — jede hat eine
einzige Aufgabe:

- **`compose.yml` (Main)** — Kern-Stack: `docker-proxy` (Socket-Proxy für die
  Admin-Steuerung), `asr` (Parakeet Python/ONNX), `diar` (CrispASR-Diarization)
  und `webapp` (GUI). Wird von `docker compose up` automatisch geladen.
- **`compose.backends.yml`** — die optionalen Backends `asr-cpp`, `crispr-qwen3`,
  `crispr-ark`, `crispr-moonshine-de`, `crispr-canary` (Voxtral: geplant), jeweils über
  **Docker-Profile** aktivierbar.
- **`compose.gpu.yml`** — GPU-Overlay (`runtime: nvidia` für alle hybriden
  Services). Nur auf Maschinen mit NVIDIA Container Toolkit einbinden.
- **`compose.oidc.yml`** — OIDC-Overlay mit Dummy-Werten (Login + Admin).
- **`compose.benchmark.yml`** — Benchmark als Einmal-Container (per Host-Cron
  oder manuell), schreibt Ergebnisse ins gemeinsame Volume.

## Warum Profile statt override.yml?

Eine `docker-compose.override.yml` wird von Compose **immer automatisch
gemergt** — die Backends wären dauerhaft Teil des Stacks. Profile halten sie
optional: definiert, aber nur gestartet, wenn `--profile <name>` gesetzt
wird. Die Admin-GUI kann die (per `--no-start` erzeugten) Container trotzdem
on demand starten/stoppen.

## Warum GPU als Overlay?

`runtime: nvidia` in der Main-Compose würde den Stack auf Maschinen ohne
NVIDIA-Runtime unstartbar machen. Das Overlay ist die einzige Stelle, an der
GPU-Zugriff vergeben wird.

## Warum OIDC als Overlay?

Ohne Login läuft PolySchnack als öffentlicher Shared Space (bewusst). OIDC
ist ein optionales Upgrade — das Dummy-Overlay macht die Aktivierung
dokumentierbar und trotzdem offensichtlich ersetzbar.

## Befehle

```bash
# Nur Kern (GUI + ONNX, CPU oder GPU via Overlay):
docker compose up -d                                   # CPU
docker compose -f compose.yml -f compose.gpu.yml up -d # GPU

# Kern + Backends (Container erzeugen, GUI startet on demand):
docker compose -f compose.yml -f compose.backends.yml \
  --profile cpp --profile qwen3 --profile ark up -d --no-start

# Kern + einzelnes Backend direkt mitstarten:
docker compose -f compose.yml -f compose.backends.yml --profile cpp up -d

# Kern + OIDC-Login (Dummy-Werte vorher ersetzen!):
docker compose -f compose.yml -f compose.oidc.yml up -d
```

## Profile im Detail

| Profil | Befehl | Startet | GPU via Overlay |
|--------|--------|---------|:---------:|
| *(kein Profil)* | `docker compose up -d` | docker-proxy + asr + diar + webapp | ✅ |
| `--profile cpp` | `docker compose -f compose.yml -f compose.backends.yml --profile cpp up -d` | + asr-cpp | ✅ |
| `--profile qwen3` | `docker compose -f compose.yml -f compose.backends.yml --profile qwen3 up -d` | + qwen3-asr | ✅ |
| `--profile ark` | `docker compose -f compose.yml -f compose.backends.yml --profile ark up -d` | + ark-asr | ✅ |
| `--profile moonshine` | `docker compose -f compose.yml -f compose.backends.yml --profile moonshine up -d` | + moonshine-de | ✅ |
| `--profile canary` | `docker compose -f compose.yml -f compose.backends.yml --profile canary up -d` | + canary-asr | ✅ |

## Hinweis

Modell-Dateien liegen in Bind-Mounts unter `./DATA/<name>-models/` (keine
Named-Volumes). Die vollständigen Service-Definitionen stehen in `compose.yml`
/ `compose.backends.yml`. Inter-Service-URLs nutzen immer den
**Container-Port** (der interne Port im Compose-Netz), nicht das
Host-Port-Mapping (z. B. `http://crispr-crispr-diar:5098`, während am Host nur `asr:5092`
und `webapp:8088` gebunden sind — diar hat gar kein Host-Port).
