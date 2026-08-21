# PolySchnack — Multi-Backend Speech-to-Text

**OpenAI-kompatible Spracherkennung mit wählbaren ASR-Backends** — von
lokalen ggml/C++-Engines bis zu eigenen Remote-API-Endpunkten. Mit Web UI,
Live-Transkription, Word-Timestamps, Sprechererkennung (Diarization),
kollaborativer Bearbeitung, OIDC-Workspaces und öffentlichem Benchmark
(WER/€-Vergleich).

Ein Befehl startet den kompletten Stack (CPU überall, GPU optional) — ohne
Code, ohne Lock-in: Backend-Wechsel per Env-Variable oder Admin-GUI, die
Qualität bleibt messbar dank integriertem Benchmark.

## Schnelleinstieg

```bash
git clone <dein-repo-url> && cd polyschnack
./polyschnack-manage.sh            # = start (GPU auto, Backends on demand)
```

Manuell: [Quickstart](quickstart.md) · Voraussetzungen: siehe Repo-`README.md`

## Dokumentations-Landkarte

| Ich will … | → hier |
|---|---|
| … die App starten | [Quickstart](quickstart.md) |
| … verstehen, wie das System aufgebaut ist | [Architektur](architecture.md) |
| … den kompletten Code verstehen (Dateien, Funktionen, Zusammenspiel) | [Code-Guide](development/code-guide.md) |
| … wissen, welche ASR-Backends es gibt | [Backend-Übersicht](backends/overview.md) + [Feature-Matrix](backends/matrix.md) |
| … alle UI-Features kennen | [Web UI & Features](webui.md) |
| … Backends/Modelle einrichten | [Modelle laden](backends/models.md) · [Compose-Referenz](compose.md) |
| … Login + Admin einrichten | [OIDC-Auth](configuration/oidc.md) · [Admin-Bereich](configuration/admin.md) |
| … alle Env-Variablen | [Konfiguration](configuration/env.md) |
| … den Benchmark verstehen | [Benchmark](benchmark/index.md) |
| … die API programmatisch nutzen | [API](API.md) |
| … Features ändern/entwickeln | [Entwicklung](development/setup.md) · [OpenSpec](development/openspec.md) |
| … warum welche Komponente gewählt wurde | [Component Decisions](component-decisions.md) |

## Danksagung

Das Projekt startete als Fork von
[istupakov/parakeet-tdt](https://github.com/istupakov/parakeet-tdt) (NVIDIA
Parakeet TDT 0.6B v3) und dessen WebUI. Seitdem kamen hinzu:
Multi-Backend-Adapter, OIDC-Auth, Diarization, Kollaboration, Benchmark und
eine modulare CrispASR-Backend-Architektur.
