# Diarization (Sprechererkennung)

Die Diarization läuft **nicht in der Webapp** (kein pyannote, kein
CUDA-torch), sondern im eigenen `diar`-Container — einem schlanken
CrispASR-Server, der nur für die Sprechererkennung zuständig ist und
unabhängig vom gewählten ASR-Backend funktioniert:

- **Im Default-Stack enthalten** (`compose.yml` → `diar`), Healthcheck aktiv
- **GPU** via Overlay (`compose.gpu.yml` → `runtime: nvidia`), sonst CPU (ggml)
- Kein HF_TOKEN nötig — die Webapp ruft nur `POST /v1/audio/transcriptions`
  mit `diarize=true&response_format=diarized_json` auf

## Methoden

Die Methode ist per `DIARIZE_METHOD` wählbar (Webapp-Env, Default
**`foxnose`** seit Change 126 — beste Testergebnisse im Real-World-Vergleich;
`pyannote` war vorher Default):

| Methode | Beschreibung |
|---------|-------------|
| `foxnose` | **Default.** WeSpeaker-ResNet34 — laut CrispASR beste Accuracy, keine externen deps. |
| `pyannote` | GGUF-Port des bekannten Modells (pyannote-seg-3.0). |
| `energy` / `xcorr` / `vad-turns` | Leichtgewichtig. Achtung: `energy`/`xcorr` brauchen **Stereo** — auf Mono wirkungslos. |

Die „Sprecheranzahl" aus der UI wird als `diarize_max_speakers` übertragen.

## Globales Speaker-Clustering (diarize_embedder) — WICHTIG

Die Webapp sendet seit Change 126 **immer** `diarize_embedder` mit
(Config: `DIARIZE_EMBEDDER`, Default `auto` = TitaNet für pyannote;
`DIARIZE_FOXNOSE_EMBEDDER`, Default `wespeaker` für foxnose). Erst dadurch
führt der Server das **globale Re-Clustering über die volle Audio** aus
(CrispASR #107/#292) — ohne Embedder sind die Labels chunk-lokal und bei
langen Aufnahmen fällt alles auf ein Label (Live-Befund 2026-08-25:
75-min-Meeting → 26/26 `SPEAKER_00`).

**Voraussetzung:** Der `diar`-Container muss eine CrispASR-Version mit
Embedder/Clustering-Unterstützung laufen (≥ der Stand mit
`diarize_embedder`-Request-Feld und globalem Re-Clustering; Referenz-Build
0.8.29). Der Embedder wird vom Server automatisch via HF-Cache geladen
(`titanet-large.gguf` bzw. `wespeaker-resnet34-lm.gguf`) — kein
HF_TOKEN nötig, aber **Internet-Zugang** beim ersten Lauf.

**Symptom-Check:** Erkennt die Diarization bei Audio > 10 min nur 1 Speaker,
loggt die Webapp eine Warnung
(`Diarization lieferte nur 1 Speaker bei … — Embedder/globales Clustering
serverseitig prüfen`). Ursache dann fast immer: Container-Version zu alt
oder Embedder-Download fehlgeschlagen (`docker logs diar` auf
`titanet|wespeaker|embedder` prüfen).

## Modell

Der Container lädt das Modell (parakeet-GGUF **q8_0**, ~640 MB) beim ersten
Start automatisch von HuggingFace in das Volume `./DATA/models/` —
das Volume muss dafür beschreibbar gemountet sein (in `compose.yml` bewusst
ohne `:ro`). Fehlt eine Datei, versucht der Entrypoint den Download bei jedem
Start erneut und gibt bei Fehlschlag eine Anleitung aus (siehe
`diar-service/entrypoint.sh`).

Manueller Download (z.B. wenn der Container keinen Internetzugang hat):

```bash
docker run --rm -v "$PWD/DATA/models:/models" alpine wget -O /models/parakeet-tdt-0.6b-v3-q8_0.gguf \
  https://huggingface.co/cstr/parakeet-tdt-0.6b-v3-GGUF/resolve/main/parakeet-tdt-0.6b-v3-q8_0.gguf
```
