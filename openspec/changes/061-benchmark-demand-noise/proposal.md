# Change 061 — ASR-Benchmark: DEMAND-Noise-Mix (SNR-Stufen)

**Status:** Proposal (Umsetzung folgt nach Change 060) · **Datum:** 2026-08-21

## Problem

Der ASR-Benchmark klassifiziert Samples nach Kanal-Charakter (clean,
transport, telefon, geraeusch …), testet aber **keine kontrollierte
Rausch-Robustheit**: Die Kategorien kommen aus der Sample-Charakteristik,
nicht aus definierten Störabständen. YouTube-Imports (Hauptnutzung!) sind
real verrauscht — die Robustheit der Backends gegen definiertes
Umgebungsrauschen ist bisher nicht messbar.

## Ziel

Den ASR-Benchmark um **kontrollierte Rauschmischung** erweitern:

- **DEMAND** (Diverse Environments Multichannel Acoustic Noise Database,
  [Zenodo](https://zenodo.org/records/1227121), 16k-Varianten; HF-Mirror
  CC-BY-4.0) — echte Umgebungsgeräusche (Küche, Metro, Büro, Verkehr).
- Mix-Methode (Picovoice-Praxis): saubere Referenz-Samples (CV/TTS-Selektion)
  + DEMAND-Noise bei **SNR 0 / 5 / 10 dB**, deterministisch (fester Seed).
- Neue Achse im Manifest (z. B. `noise: clean|snr0|snr5|snr10` +
  `noise_env`), gleiche Referenztexte → WER-Differenz = Rausch-Robustheit.
- Kein neuer Container: Mix zur Benchmark-Zeit (wie Seed-Skript), Manifest-
  Version wird erhöht (Manifeste sind immutable).

## Umsetzung (Skizze)

1. `benchmark/scripts/noise_mix.py`: lädt DEMAND-Teilmenge (3–5 Umgebungen,
   ~60 s je), mixt mit festem Seed auf Ziel-SNR, schreibt WAVs + erweitert
   die Selektion (`selection/noise_v2.json` o. ä.).
2. Auswertung: WER nach SNR-Stufe gruppieren (Robustheits-Kurve je Backend).
3. Doku: `docs/benchmark/index.md` (Rausch-Achse), Modelle/Backends-Vergleich.

## Referenzen

- DEMAND: [Zenodo 1227121](https://zenodo.org/records/1227121) ·
  [HF-Mirror CC-BY-4.0](https://huggingface.co/datasets/voice-biomarkers/DEMAND-acoustic-noise)
- Mix-Methodik: [Picovoice voice-activity-benchmark](https://github.com/Picovoice/voice-activity-benchmark)
  (0-dB-SNR-Mix) · VAD-Benchmark-Vorarbeit aus Change 060
  (`benchmarks/vad/`)
