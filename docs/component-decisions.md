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

## VAD-Benchmark V3 — offizielles Testset-Artefakt + FSMN-VAD (Change 063, 2026-08-21)

**V3-Testset (101 Samples):** 31 DE-Synth (Stille-Insertion), 60 DEMAND-SNR
(SNR 0/5/10 dB auf ALLEN Basis-Samples × Küche/Metro), 1 Babble, 2 TEN,
4 Noise, 3 MUSAN-Musik — deterministisch, als GitHub-Release
(`tilllt/vad-benchmark-data`, v3, SHA256 im Release).

| Engine | Lizenz | F1 (mean) | FP-Speech (s) | RTF |
|---|---|---|---|---|
| **Silero-onnx** | MIT | **0,987** | **0,0** | 0,033 |
| Energy-Baseline | — | 0,982 | 157,6 | 0,001 |
| WebRTC (GMM) | BSD | 0,979 | 135,2 | 0,0002 |
| **FSMN-VAD (FunASR)** | Apache-2.0 | 0,975 | 12,2 | 0,106 |
| HumAware-VAD | MIT | 0,894 | 16,0 | 0,141 |
| TEN VAD (Referenz) | Apache-2.0+Agora | 0,785 | 7,5 | 0,018 |
| speechbrain CRDNN (EN) | Apache-2.0 | 0,755 | 0,0 | 0,153 |

**Einordnung:**
- **Silero-onnx gewinnt auch auf dem größeren V3-Set** (F1 0,987, 0,0 s FP) —
  die Produktivwahl bleibt bestätigt.
- **FSMN-VAD ist die einzige lizenz-saubere echte Alternative** (Apache-2.0,
  multilingual): Qualität fast gleichauf (0,975), aber **12,2 s FP** (erkennt
  Musik/Noise als Sprache) und **~3× langsamer als Silero** (RTF 0,106 vs.
  0,033 auf CPU) → für Silence-Trimming in der Webapp nicht besser.
- **Kein eigenes Training** bleibt bestätigt (HumAware-Feintuning verliert
  weiterhin: 0,894 vs. 0,987).
- **„Die besseren Modelle" aus Blogs (TEN VAD) verlieren im eigenen Test**
  (0,785) — Blog-Benchmarks (Picovoice etc.) sind vendor-freundlich.

**Quellen:** eigener Lauf `benchmarks/vad/out/results_v3_public.md`
(2026-08-21) · [FSMN-VAD (FunASR, Apache-2.0)](https://huggingface.co/funasr/fsmn-vad)

## VAD-Benchmark V3.1 — Common-Voice-Basis + public/held-out-Split (Change 064, 2026-08-21)

**Motivation:** V1–V3 basierten nur auf Piper-TTS (synthetisch, ein Sprecher).
Für die Produktiv-Realität (Nutzer laden eigene Aufnahmen hoch) ist echte
Sprache mit Mikrofon-/Raumrauschen die realistischere Messung. Die 24 lokal
vorhandenen Common-Voice-DE-WAVs (CC0, akzent/child/clean, Seed-42-Auswahl
aus dem ASR-Testset) sind die natürliche zweite Basis — pur
(Stille-Insertion, exakte GT) UND kontaminiert (DEMAND-SNR 0/5/10 dB; die GT
bleibt exakt, da die Speech-Regionen deterministisch bekannt sind).

**public/held-out-Split (Change 064):** deterministischer Split (Seed 42,
60/40). Nur der **public-Teil** (235 Samples) erscheint in GitHub-Release/
ZIP/Repo/Container-Images; der **held-out-Teil** (126 Samples: andere
Stille-Insertionen + frische TTS-Varianten, nie veröffentlicht) existiert nur
lokal (`assets/v3-heldout/`, gitignored) und optional auf der KI-Box. Grund:
Sobald ein Testset öffentlich ist, kann es in Trainingsdaten einfließen
(Leakage) → die Benchmark-Zahlen wären nicht mehr ehrlich. `run_benchmark.py
--split heldout` lädt heldout nie vom Release und bricht ohne lokales
Verzeichnis ab. Das Repo/Mirror (GitHub, Harbor) enthält niemals
held-out-Audio.

**Release-Format für externe User:** `vad-benchmark-v3.1-public.zip`
(Release v4) = public-WAVs + `testset.json` (GT + `source` je Sample) +
`PROVENANCE.md` (Quellen/Lizenzen/Seeds/SHA256) + `SHA256SUMS` +
`results_v3_public.json`.

**Ergebnisse (final, V3.1-Lauf 2026-08-21, 7 Engines):**

*public (235 Samples, inkl. 144 SNR-Mixe + Noise/Musik-FP):*

| Engine | F1 | B-Start (med ms) | B-Ende (med ms) | FP-Speech (s) | RTF |
|---|---|---|---|---|---|
| **Silero-onnx** | **0,995** | 32 | 64 | **0,0** | 0,022 |
| WebRTC (GMM) | 0,987 | 22 | 90 | 135,2 | 0,0003 |
| Energy-Baseline | 0,964 | 16 | 16 | 157,6 | 0,0005 |
| HumAware-VAD | 0,945 | 32 | 32 | 16,0 | 0,054 |
| FSMN-VAD | 0,918 | 72 | 164 | 12,2 | 0,032 |
| TEN VAD (Referenz) | 0,889 | 126 | 50 | 7,5 | 0,013 |
| speechbrain CRDNN (EN) | 0,697 | 40 | 776 | 0,0 | 0,062 |

*heldout (126 Samples, nie veröffentlicht — frische Insertionen + CV):*

| Engine | F1 | B-Start (med ms) | B-Ende (med ms) | RTF |
|---|---|---|---|---|
| **Silero-onnx** | **0,998** | 32 | 96 | 0,018 |
| WebRTC (GMM) | 0,988 | 34 | 107 | 0,0002 |
| HumAware-VAD | 0,980 | 32 | 32 | 0,038 |
| Energy-Baseline | 0,956 | 16 | 32 | 0,0005 |
| TEN VAD (Referenz) | 0,932 | 126 | 72 | 0,012 |
| FSMN-VAD | 0,898 | 104 | 712 | 0,020 |
| speechbrain CRDNN (EN) | 0,561 | 72 | 824 | 0,039 |

**Kernerkenntnis V3.1:** Silero-onnx gewinnt auf beiden Splits (public 0,995 /
heldout 0,998) und bleibt **0,0 s FP** — auch auf den 24 echten
Common-Voice-Aufnahmen (TTS war also keine künstlich einfache Bedingung).
FSMN-VAD (einzige lizenz-saubere Alternative) bleibt bei 0,918 public /
12,2 s FP — Qualität gut, aber FP-Risiko und RTF-Vorteil sprechen weiter
gegen einen Wechsel. heldout-Zahlen sind die ehrliche finale Bewertung
(kein Leakage-Risiko), public-Zahlen dienen externen Usern zur
Reproduzierbarkeit.

**Quellen:** [Common Voice DE (CC0-1.0)](https://commonvoice.mozilla.org/de) ·
`cv_selection.json` (Seed 42) · eigener Lauf (2026-08-21)
