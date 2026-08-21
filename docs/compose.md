# Compose-Referenz

Der Stack ist bewusst in **fünf Compose-Dateien** aufgeteilt — jede hat eine
einzige Aufgabe:

- **`compose.yml` (Main)** — Kern-Stack: `docker-proxy` (Socket-Proxy für die
  Admin-Steuerung), `asr` (Parakeet Python/ONNX), `diar` (CrispASR-Diarization)
  und `webapp` (GUI). Wird von `docker compose up` automatisch geladen.
- **`compose.backends.yml`** — die optionalen Backends `crispr-pk-cpp`,
  `crispr-qwen3`, `crispr-ark`, `crispr-moonshine-de`, `crispr-canary`,
  `crispr-voxtral`, `crispr-whisper` sowie der Tor-Sidecar `ps-tor`
  (YouTube-Import-Fallback, Change 043), jeweils über **Docker-Profile**
  aktivierbar.
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
  --profile crispr-pk-cpp --profile crispr-qwen3 --profile crispr-ark up -d --no-start

# Kern + einzelnes Backend direkt mitstarten:
docker compose -f compose.yml -f compose.backends.yml --profile crispr-pk-cpp up -d

# Kern + OIDC-Login (Dummy-Werte vorher ersetzen!):
docker compose -f compose.yml -f compose.oidc.yml up -d
```

## Profile im Detail

| Profil | Befehl | Startet | GPU via Overlay |
|--------|--------|---------|:---------:|
| *(kein Profil)* | `docker compose up -d` | docker-proxy + asr + diar + webapp | ✅ |
| `--profile crispr-pk-cpp` | `docker compose -f compose.yml -f compose.backends.yml --profile crispr-pk-cpp up -d` | + crispr-pk-cpp | ✅ |
| `--profile crispr-qwen3` | `docker compose -f compose.yml -f compose.backends.yml --profile crispr-qwen3 up -d` | + crispr-qwen3 | ✅ |
| `--profile crispr-ark` | `docker compose -f compose.yml -f compose.backends.yml --profile crispr-ark up -d` | + crispr-ark | ✅ |
| `--profile crispr-moonshine-de` | `docker compose -f compose.yml -f compose.backends.yml --profile crispr-moonshine-de up -d` | + crispr-moonshine-de | ✅ |
| `--profile crispr-canary` | `docker compose -f compose.yml -f compose.backends.yml --profile crispr-canary up -d` | + crispr-canary | ✅ |
| `--profile crispr-voxtral` | `docker compose -f compose.yml -f compose.backends.yml --profile crispr-voxtral up -d` | + crispr-voxtral | ✅ |
| `--profile crispr-whisper` | `docker compose -f compose.yml -f compose.backends.yml --profile crispr-whisper up -d` | + crispr-whisper | ✅ |
| `--profile ps-tor` | `docker compose -f compose.yml -f compose.backends.yml --profile ps-tor up -d` | + ps-tor (startet on demand) | — |

## Zusammenspiel: `backends.yaml` ↔ `compose.backends.yml` ↔ `POLYSCHNACK_BACKENDS`

Drei Ebenen mit getrennten Aufgaben:

| Ebene | Datei | Aufgabe |
|-------|-------|---------|
| **Katalog** | `webapp/app/backends.yaml` | was es gibt: Name, `compose_profile`, Port, `model_files` (Download-URLs), Capabilities, Adapter |
| **Container** | `compose.backends.yml` | wie es läuft: Image, Volumes, Ports, Healthcheck, Profil |
| **Auswahl** | `.env` → `POLYSCHNACK_BACKENDS` | was läuft: aktiviert Profile + Modell-Download |

`backends.yaml` ist die **Single Source of Truth**: Das Manage-Skript leitet
daraus Profile (`compose_profile`) und Modell-Downloads (`model_files`) ab —
es gibt keine hartkodierte Modell-Liste. Die Webapp (Registry, Feature-Matrix,
Benchmark) liest dieselbe Datei. `POLYSCHNACK_BACKENDS` wählt nur aus
(Namen, die weder im Katalog noch als Compose-Profil existieren, erzeugen
eine Warnung). `selfupdate` zieht Skript **und** `backends.yaml`.

**Konsequenz — neues Backend = 3 Schritte:** YAML-Block in `backends.yaml` →
Service in `compose.backends.yml` → Name in `POLYSCHNACK_BACKENDS`. Eigenes
Modell = nur die URL in `model_files` ändern, dann `models`.

## Hinweis

Modell-Dateien liegen in **Bind-Mounts**: GGUF-Modelle aller Backends +
diar + aligner gemeinsam in `./DATA/models` (Backends mounten read-only),
das ONNX-Modell in `./DATA/parakeet-models`, Audio/Aufnahmen in
`./DATA/poc-data` — keine Named-Volumes. Inter-Service-URLs nutzen immer
den **Container-Port** im Compose-Netz (z. B. `http://crispr-diar:5098`),
nicht das Host-Port-Mapping.
