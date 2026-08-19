# Engineering Spec — Delta für Change 027

## ADDED Requirements

### REQ-BENCH-032: Whisper/WhisperX/Voxtral als Benchmark-Suite-Backends
`Benchmark-Auswertung` · `must`

Die Benchmark-Suite misst folgende Backends auf identischem Audio
(alle Manifest-Kategorien, Sprachwahl je Kategorie de/en):

- `whisper-large-v3` (faster-whisper large-v3, aufdock-Server-Image,
  Port 8000, OpenAI-kompatible API)
- `whisperx` (faster-whisper large-v3 + wav2vec2-Forced-Alignment;
  Transkriptionstext = large-v3, Alignment separat bewertet)
- `voxtral-mini-realtime` (Voxtral-Mini-4B-Realtime-2602 via vLLM,
  Port 8000, `--served-model-name whisper-1`)

Metriken je Backend: WER (gesamt/je Kategorie/je Sample), RTF,
Startzeit, Kosten; Ergebnisdateien `result_benchmark_<name>[_suffix].json`
unter `/opt/data/vast-benchmarks/logs/`. Suite unterstützt
`--instance <id>` (Reuse bestehender Instanz, kein Auto-Destroy).

### REQ-BENCH-033: Container-Einbindung als PolySchnack-Backends
`PolySchnack-Stack` · `must`

Nach bestandener Phase A/B werden die Backends als Container in den
PolySchnack-Stack eingebunden:

- Images `ghcr.io/tilllt/polyschnack-asr-{whisper,whisperx,voxtral}`,
  einheitlicher API-Vertrag: `POST /v1/audio/transcriptions`
  (multipart `file`+`language`+`model`) → `{text}` (WhisperX zusätzlich
  `segments[]` mit Wort-Timestamps); `GET /health`.
- Compose-Services (Ports 5098–5100) mit GPU-Ressourcenlimits und
  on-demand-Start über die Admin-GUI (inkl. VRAM-Check).
- GUI-Backend-Auswahl erweitert; Segment-Anzeige nutzt Wort-Timestamps,
  falls vom Backend geliefert.

### REQ-BENCH-034: Kommerzieller Lizenz-Check
`PolySchnack-Stack` · `must`

Vor Aufnahme eines Backends in den Produktiv-Stack wird die kommerzielle
Nutzbarkeit aller Komponenten mit Quellen belegt:

- Whisper (MIT), faster-whisper (MIT), Voxtral-Mini-4B-Realtime-2602
  (Apache-2.0), vLLM (Apache-2.0), WhisperX (BSD-2-Clause).
- **wav2vec2-Alignment-Modelle:** Modelle mit CC-BY-NC-/nicht-kommerzieller
  Lizenz (häufig bei deutschen xlsr-Feintunes) sind für PolySchnack
  unzulässig; ohne kommerziell taugliches deutsches Alignment-Modell
  wird WhisperX nur intern gemessen und die Timestamp-Funktion über den
  bestehenden Aligner abgebildet.
- pyannote-Modelle: Lizenz prüfen; Diarisierung wird nicht dupliziert
  (bestehendes Diar-Backend).

### REQ-BENCH-035: Entscheidungen dokumentiert + Re-Evaluation
`Dokumentation` · `must`

- Ergebnisse und Aufnahme-Entscheidungen je Backend (ja/nein, mit
  Quellen) in `docs/component-decisions.md` (Change-021-Methode).
- Benchmark-Report enthält die neuen Backends mit selbstgemessenen
  Werten; Fremdwerte (FQS-Studie) bleiben als solche markiert.
- Re-Evaluation bei neuen Releases der Modelle/Engines.
