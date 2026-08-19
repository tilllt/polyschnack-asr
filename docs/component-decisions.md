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
