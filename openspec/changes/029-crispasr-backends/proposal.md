# Change 029 — CrispASR-Backends: Voxtral (voxtral4b) + Whisper als Backend-Optionen

## Problem

1. **Voxtral-Backend (vLLM) hängt deterministisch** bei bestimmten Audios
   (vllm-project/vllm #52926: „empty multimodal embeddings" → Decode endet
   nie, „Remote end closed connection without response"). 2× reproduziert
   bei `funk_tts_funk_008.wav`, weitere Samples zeigen dasselbe Muster
   (Sample 151/210, 352 s Timeout, leeres Ergebnis). Der vLLM-Pfad ist für
   einen produktiven PolySchnack-Backend-Container nicht tragfähig.
2. **faster-whisper-Image (polyschnack-asr-whisper) startet auf vast nicht**:
   Benchmark-Instanz 48097471 war 40 min nicht bereit (Port zu) →
   TimeoutError, Instanz destroyed. Ursache offen (Modell-Download/Image).
3. **User-Regel (2026-08-19):** Wenn es für den Mechanismus ein
   crispASR-basiertes Docker gibt, bevorzugen wir es immer — außer es ist
   langsamer oder hat weniger Features. CrispASR (v0.8.29) unterstützt
   `voxtral4b` (= Mistral Voxtral-Mini-4B-Realtime-2602, verifiziert per
   Binary-`--help`) und `whisper` (OpenAI Whisper GGUFs) — mit Server-Modus,
   VAD, Diarisierung, LID, Interpunktion/Truecasing, Alignment: mehr
   Features als vLLM, gleiche ggml-Engine wie transcribe.cpp.

## Ziel

1. Zwei neue Backend-Optionen für PolySchnack als CrispASR-Images,
   per CI auf Harbor gepusht:
   - `polyschnack-asr-voxtral` (CrispASR `--backend voxtral4b`, Port 5100)
   - `polyschnack-asr-whisper-crisp` (CrispASR `--backend whisper`, Port 5101)
2. Einbindung als Compose-Profile (`crispr-voxtral`, `crispr-whisper`)
   und in die Webapp-Backend-Registry (`backends.yaml`, Adapter
   `CrispAsrHttpClient` — existiert bereits für ark/canary/moonshine).
3. vLLM-Backend bleibt als Benchmark-/Vergleichspfad erhalten
   (start_timing_vast.py), wird aber NICHT als Compose-Backend eingebunden.

## Was sich für Nutzer/Entwickler ändert (Verhaltens-Delta)

- Admin-GUI: zwei neue Backend-Optionen (crispr-voxtral, crispr-whisper)
  mit Start/Stop-Button, Modell-Download via `polyschnack-manage.sh models`.
- Neue Images unter harbor.rand0m.me/public/ + ghcr.io/tilllt/ (Mirror).
- Kein Verhaltens-Delta für bestehende Backends.

## Abgrenzung / Ehrlichkeit

- Kein Benchmark der neuen Backends in diesem Change (eigener Change /
  vast-Lauf nach Abnahme der Images). Kein Umbau des bestehenden
  faster-whisper-Images (build-whisper bleibt; dessen vast-Startproblem
  wird separat untersucht — `crispr-whisper` ist die CrispASR-Alternative).
- Quantisierung: Q8_0 für Voxtral (4,7 GB, WER-neutral laut
  handy-computer-Messung 2,07 % vs. 2,08 % BF16 auf LibriSpeech test-clean);
  F16/BF16 bleiben optional über `model_files`-Erweiterung.

## Specs-Delta

`ADDED` — `specs/engineering/spec.md`: REQ-WEB-037 (crispr-voxtral),
REQ-WEB-038 (crispr-whisper)
