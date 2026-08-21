# Component Decisions

Evidenzbasierte Komponentenentscheidungen (Anforderung aus Change 021:
„Eine Entscheidung ohne Quellenbeleg ist nicht zulässig").

## ASR — FQS-Referenzvergleich: eigene Backends vs. kommerzielle Plattformen

**Datum:** 2026-08-19 · **Quelle:** Change 024, Benchmark-Repo
`polyschnack-benchmark` (Sektion „FQS-Referenzvergleich" im Report,
`results/fqs_run.json`)

**Methode:** Die 4 öffentlichen FQS-Ausschnitte (Zenodo 10209813, 2 DE + 2 EN,
~102 s gesamt) wurden mit allen PolySchnack-Backends transkribiert (frische
vast.ai-Instanz je Backend, RTX 3060, EU; `backend_benchmark_full.py
--categories fqs_de,fqs_en`). Die WER der kommerziellen Anbieter wurden auf
**denselben Ausschnitten** aus den publizierten Tool-Transkripten der
FQS-Studie (Tabellen 5/6, Wollin-Giering et al. 2024) mit jiwer berechnet.

### Ergebnisse — WER je DE-Ausschnitt (niedriger = besser) und RTF

| System | DE-Ex1 | DE-Ex2 | Ø DE | RTF |
|---|---|---|---|---|
| **crispr-pk-cpp (Parakeet GGUF)** | 0,152 | 0,153 | **0,152** | 0,025 |
| **ps-pk-onnx (Parakeet ONNX)** | 0,121 | 0,202 | **0,161** | 0,065 |
| crispr-canary | 0,379 | 0,331 | 0,355 | 0,037 |
| crispr-moonshine-de | 0,697 | 0,532 | 0,615 | 0,074 |
| — Referenz kommerziell (FQS 2022) — | | | | |
| Whisper large-v2 (Open-Source) | 0,212 | 0,194 | 0,203 | — |
| Sonix | 0,227 | 0,250 | 0,239 | — |
| Amberscript / Happy Scribe / F4x | 0,258 | 0,315 | 0,286 | — |
| Trint | 0,258 | 0,355 | 0,306 | — |
| NVivo | 0,288 | 0,347 | 0,317 | — |
| Dragon | 0,758 | 0,815 | 0,786 | — |

**Einordnung (ehrlich, mit Einschränkungen):**
- **Deutsch:** Die Parakeet-Backends (cpp/onnx) liegen mit Ø-DE-WER 0,15–0,16
  **deutlich unter allen kommerziellen Anbietern der Studie** (bester
  kommerzieller Wert: Whisper 0,203, bester SaaS: Sonix 0,239). canary
  (0,355) liegt auf dem Niveau der mittleren kommerziellen Anbieter,
  moonshine-de (0,615) nur vor Dragon.
- **Englisch:** Die eigenen Backends sind DE-optimiert und verlieren klar
  gegen die kommerziellen EN-Werte (Sonix/Whisper ≈ 0,03 vs. onnx 0,47 /
  cpp 0,44). canary transkribiert EN als Deutsch (WER > 1) — EN-Input ist
  für das DE-Modell ungeeignet.
- **Einschränkungen:** Ausschnitte ≠ volle 5-Minuten-Interviews (publizierte
  Studienwerte nicht direkt vergleichbar); Tools von 2022; ~102 s Audio =
  keine statistische Aussage, Orientierung der Modellklasse. Die Werte
  bestätigen qualitativ die Nacht-Suite 2026-08-18 (Parakeet-Backends
  vorn, canary/moonshine dahinter).

**Kosten des Messlaufs:** 4 Instanzen × ~10–15 min ≈ 0,02 $ gesamt.

**Entscheidung:** Kein Backend-Wechsel nötig — die Evidenz bestätigt die
aktuelle Empfehlung: **Parakeet (cpp/onnx) als primäre DE-Backends**,
canary als Alternative. moonshine-de bleibt nur für Sonderfälle
(extreme Echtzeit-Anforderung) relevant. EN-Sprachmaterial gehört über
ein EN-fähiges Backend verarbeitet (aktuell nicht im Fokus).

## VAD für Silence-Trimming (Change 060, 2026-08-21)

**Ausgangslage:** Das Webapp-Image war auf 3,06 GB komprimiert gewachsen —
das PyPI-Paket `silero-vad>=6.0.0` zog torch/torchaudio/triton transitiv in
den `uv sync`-Layer (`/.venv` = 4,9 GB unkomprimiert, verifiziert per
Layer-Streaming). Genutzt wird VAD nur für Silence-Trimming (3 Aufrufe in
`service.py`), `detect_speech_regions` ist ungenutzt.

**Vergleich (eigener Benchmark, `benchmarks/vad/`, 59 Samples: 31 DE-Synth
mit deterministischer Stille-Insertion + exakter GT, 18 SNR-Mix
(DEMAND-Küche/Metro bei 0/5/10 dB), 1 Babble (2-Sprecher-Overlay),
2 TEN-Testset, 4 Noise-FP inkl. DEMAND, 3 MUSAN-Musik-FP):**

| Engine | F1 (mean) | Boundary-Start (med. ms) | Boundary-Ende (med. ms) | FP-Speech (s) | RTF |
|---|---|---|---|---|---|
| **Silero-onnx (Webapp)** | **0,976** | 16 | 24 | **0,0** | 0,022 |
| TEN VAD (sherpa-Port) | 0,824 | 110 | 32 | 7,5 | 0,013 |
| WebRTC (GMM) | 0,962 | 8 | 24 | 135,2 | 0,0002 |
| HumAware-VAD (Silero-Feintuning) | 0,892 | 32 | 52 | 16,0 | 0,36 |
| speechbrain CRDNN (EN) | 0,558 | 8 | 24 | 0,0 | 0,49 |
| Energy-Baseline | 0,968 | 8 | 16 | 157,6 | 0,0008 |

**Einordnung:**
- **Silero-onnx gewinnt auch unter Härtebedingungen:** bestes F1 (0,976),
  **0,0 s FP auf 4+3 Noise/Musik-Samples und im Babble-Overlay** — auch bei
  SNR 0 dB (DEMAND) bleibt die Detektion stabil. Die harten Szenarien
  (Babble/Musik/0-dB-Rauschen) haben Silero nicht geknackt.
- **Feintuning-Frage empirisch beantwortet:** HumAware-VAD ist exakt der
  Fall „Silero feintunen gegen Humming/Babble" (MIT, JIT) — und **verliert
  klar gegen das Basis-Silero** (F1 0,892 vs. 0,976; 16 s FP vs. 0,0 s;
  Boundary-Start 32 ms vs. 16 ms). Das Feintuning half auf der
  Humming-Aufgabe, kostete aber auf unserem Mix (Boundaries, SNR, Musik).
  → **Eigenes Training/Feintuning ist nicht gerechtfertigt**; Silero-onnx
  bleibt, der Container-Benchmark (Change 062) misst weitere
  Referenz-Modelle weiterhin mit (auch lizenz-inkompatible wie TEN VAD).
- **TEN VAD:** schlechteres F1 (0,824), 7,5 s FP im sherpa-Port. Unabhängig
  davon ist die **Lizenz ein Ausschlusskriterium**: Apache-2.0 mit
  Agora-Zusatzklauseln — Punkt 1 verbietet Deploy, das mit Agoras Angeboten
  konkurriert (self-hosted ASR = kollidierend). Nur Benchmark-Referenz.
- **WebRTC/Energy:** Boundary-technisch gut, aber **versagen auf
  Noise/Musik (135 s / 158 s FP)** — keine Alternative für echte Audios.
- **speechbrain CRDNN:** F1 0,558 (EN-only, DE-TTS unsauber erkannt).

**Entscheidung:** **Silero VAD bleibt das Modell**, läuft künftig direkt
via **onnxruntime** (silero_vad.onnx, MIT, 2,3 MB) statt über das
torch-ziehende PyPI-Paket. Image-Einsparung ≈ 2,5–3 GB. TEN VAD und
Energy scheiden aus (Lizenz bzw. Rausch-Anfälligkeit). CrispASR-nativ
(`--vad`, Silero-GGUF) bleibt als Option für eine spätere Backend-Verlegung
notiert (unverändert Silero-Qualität).

**Quellen:** eigener Benchmark-Lauf `benchmarks/vad/out/results.md`
(2026-08-21) · [silero-vad (MIT)](https://github.com/snakers4/silero-vad) ·
[TEN-VAD-Lizenz](https://github.com/TEN-framework/ten-vad/blob/main/LICENSE)
· [sherpa ten-vad-Port (pitch=0)](https://k2-fsa.github.io/sherpa/onnx/vad/ten-vad.html)
· Picovoice-Methodik (FPR/TPR) [voice-activity-benchmark](https://github.com/Picovoice/voice-activity-benchmark)
