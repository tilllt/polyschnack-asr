# Change 027 — Tasks

## Phase A: Benchmark (selbstgemessene Werte)
- [ ] Whisper large-v3: Suite-Lauf über alle Manifest-Kategorien
      (auf der Walzen-Vortranskriptions-Instanz, `--instance`-Reuse)
- [ ] Voxtral-Mini-4B-Realtime: Suite-Lauf (24-GB-Instanz, parallel,
      läuft) — REST-Transcriptions-API mit vLLM verifizieren
- [ ] WhisperX: Server-Image festlegen (Eigenbau-Dockerfile), Suite-
      Lauf (Transkriptionstext) + separater Alignment-Test (Wort-
      Timestamps)
- [ ] Ergebnisse reviewen: WER/RTF/Kosten je Kategorie, Vergleich mit
      eigenen Backends + FQS-Kommerzwerten

## Phase B: Lizenz-Check (kommerziell)
- [ ] Whisper (MIT), faster-whisper (MIT), Voxtral (Apache-2.0),
      vLLM (Apache-2.0), WhisperX (BSD-2-Clause) mit Quellen belegen
- [ ] wav2vec2-Alignment-Modelle DE: Lizenzprüfung; kommerziell
      taugliches deutsches Alignment-Modell suchen (Apache/MIT) oder
      Ausweichweg: bestehender Qwen3-Aligner für Timestamps
- [ ] pyannote-Modelle (falls WhisperX-Diar in Betracht gezogen):
      Lizenz prüfen; Diar-Duplikation vermeiden
- [ ] Ergebnis in `docs/component-decisions.md` (Entscheidung je
      Backend: aufnehmen ja/nein, mit Quellen)

## Phase C: Container-Einbindung (PolySchnack)
- [ ] Dockerfiles `polyschnack-asr-{whisper,whisperx,voxtral}` im
      PolySchnack-Repo (OpenAI-kompatible API, /health)
- [ ] CI: Images bauen + nach Harbor/GHCR pushen (bestehendes Muster)
- [ ] Compose-Services (Ports 5098–5100, GPU-Limits, on-demand-Start
      mit VRAM-Check)
- [ ] GUI: Backend-Auswahl erweitern; Segment-Anzeige mit Wort-
      Timestamps (WhisperX), falls verfügbar
- [ ] Backend-Switch-Test (GUI + API) gegen laufendes System

## Phase D: Doku + Abschluss
- [ ] Benchmark-Report: neue Backends in Kategorie-Tabellen
- [ ] Businessplan 3.4: neue Backends + Entscheidungen (falls relevant)
- [ ] Commit + Push (pk-asr + polyschnack + benchmark), CI prüfen und
      melden; Re-Evaluation bei neuen Releases (Change 021)
