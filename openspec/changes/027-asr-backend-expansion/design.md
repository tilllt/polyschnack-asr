# Change 027 — Design

## Backends im Überblick

| Backend | Modell/Engine | Image (Suite) | API | Lizenz | VRAM |
|---|---|---|---|---|---|
| `whisper-large-v3` | faster-whisper large-v3 | `aufdock/faster-whisper-server:latest-cuda` (Port 8000, env ASR_MODEL/ENGINE/LANGUAGE) | OpenAI-kompatibel `/v1/audio/transcriptions` + `/health` | MIT (Whisper), MIT (faster-whisper) | ~6–8 GB (int8) |
| `whisperx` | faster-whisper large-v3 + wav2vec2-Forced-Alignment (+ pyannote optional) | eigenes Image (Basis: PolySchnack-ASR-Image bzw. WhisperX-Dependencies), Port 5098 | OpenAI-kompatibel; Segment-Ausgabe mit Wort-Timestamps | BSD-2-Clause (WhisperX); **Alignment-Modell DE: Lizenz prüfen** (CC-BY-NC-Hürde) | ~8–10 GB |
| `voxtral-mini-realtime` | Voxtral-Mini-4B-Realtime-2602 via vLLM | `vllm/vllm-openai:latest` (Port 8000, Mistral-Flags, `--served-model-name whisper-1`) | OpenAI-kompatibel (vLLM SupportsTranscription; WebSocket-Realtime optional) | Apache-2.0 | ~10–12 GB (bf16), 16 GB+ empfohlen |

## Phase A — Benchmark (Suite)

- Backend-Definitionen in `start_timing_vast.py` (bereits registriert),
  Suite-Aufruf mit `--instance <id>` (bereits implementiert; keine
  Neu-Miete bei Reuse, kein Auto-Destroy im Reuse-Modus).
- **Whisper large-v3:** Läuft auf der Walzen-Vortranskriptions-Instanz
  (nach den 33 Walzen) über alle Manifest-Kategorien.
- **Voxtral:** Eigene 24-GB-Instanz (RTX 3090/4090/A6000/L4, EU) parallel;
  Orchestrierung `voxtral_benchmark.py` (Miete → Suite `--instance` →
  Destroy).
- **WhisperX:** nach Klärung des Server-Images + Alignment-Modells
  (Lizenz!); Messung des Transkriptionstexts (large-v3) + separater
  Alignment-Qualitätstest (Wort-Timestamps vs. manuelle Segmente).
- Metriken je Backend: WER gesamt/je Kategorie/je Sample, RTF,
  Provisioning-Startzeit, Kosten (result_benchmark_<name>.json).
- Sprachwahl je Kategorie: `en` für *_en-Kategorien, sonst `de`
  (multipart_post, bereits implementiert).

## Phase B — Lizenz-Check (kommerziell, Change-021-Methode)

Zu prüfen und mit Quellen zu belegen (docs/component-decisions.md):

1. **Whisper large-v3** (MIT), **faster-whisper** (MIT),
   **Voxtral** (Apache-2.0) — unkritisch.
2. **WhisperX** (BSD-2-Clause) — Code unkritisch; **Abhängigkeiten**:
   wav2vec2-Alignment-Checkpoints (EN via torchaudio: Apache-2.0;
   DE xlsr-Modelle oft CC-BY-NC-4.0 → nicht kommerziell).
   → Kriterium: deutschsprachiges Alignment-Modell mit kommerziell
   tauglicher Lizenz finden (z. B. Apache/MIT-lizenzierte xlsr-/wav2vec2-
   Feintunes oder eigenes Alignment-Training) ODER WhisperX nur intern
   messen und die Timestamp-Funktion über den bestehenden
   Aligner (Qwen3-Forced-Aligner) abbilden.
3. **pyannote-Diarisierung** (WhisperX-Option): Code MIT; Modelle
   (`pyannote/speaker-diarization-3.1`) Lizenz prüfen — in PolySchnack
   existiert bereits ein Diar-Backend (crispr-diar), daher keine
   Duplikation vorgesehen.
4. **vLLM** (Apache-2.0) — unkritisch; Image `vllm/vllm-openai` aus
   öffentlicher Registry.

## Phase C — Container-Einbindung (PolySchnack-Stack)

- Neue Images `ghcr.io/tilllt/polyschnack-asr-{whisper,whisperx,voxtral}`
  im PolySchnack-Repo (docker/polyschnack-asr-*), Basis nvidia-cuda
  bzw. bestehendes ASR-Basis-Image; CI baut + pusht (Harbor/GHCR,
  bestehendes Muster der übrigen Backends).
- **API-Vertrag** (einheitlich): `POST /v1/audio/transcriptions`
  (multipart, `file`+`language`+`model`), Response `{text}` bzw.
  WhisperX zusätzlich `segments[]` mit Wort-Timestamps; `GET /health`.
- **Compose:** Service je Backend (Port 5098–5100), GPU-Limits,
  Restart-Policy; „on demand"-Start durch Admin-GUI (bestehendes
  Konzept) mit VRAM-Check.
- **GUI:** Backend-Liste im Transkriptions-Dialog erweitern; Ergebnis-
  Segment-Anzeige nutzt Wort-Timestamps, falls vorhanden.
- Entscheidung je Backend (aufnehmen ja/nein) erst NACH Phase A+B
  (Benchmark + Lizenz) — Anti-Gaming und Seriosität wie gehabt.

## Offene Fragen

- WhisperX-Server-Image: Eigenbau (Dockerfile) vs. Community-Image —
  Eigenbau bevorzugt (Reproduzierbarkeit, Kontrolle der Abhängigkeiten).
- Alignment-Modell DE mit kommerziell-tauglicher Lizenz — Recherche
  Phase B; ohne Fund: WhisperX nur intern, Timestamps über bestehenden
  Aligner.
- Voxtral-REST-Transkription: Verifikation, dass vLLM die
  Multipart-Transcriptions-API für das Realtime-Modell akzeptiert
  (läuft im aktuellen Benchmark-Lauf).
