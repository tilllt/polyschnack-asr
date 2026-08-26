# Change 081: Test-Set-Bereinigung — Ramona raus (ASR + VAD), Provenienz im Dateinamen

## Problem

1. **Installiertes ASR-Benchmark-Paket ist veraltet:** `benchmark_data_pkg` v1
   (21.08. 17:46) wurde VOR der TTS-Regeneration (22.08. 07:06) gebaut und
   enthält noch **66 Ramona-TTS-Samples** — akustisch bestätigt (User 26.08.,
   Hörproben: de_01 = Ramona; zahlen_002 im Paket Hash 405a78f5 ≠ aktuelle
   VibeVoice-Quelle 1d729b57). Die **aktuellen Quellen sind bereits sauber**
   (Thorsten gerade / VibeVoice-f ungerade, Change 080).
2. **VAD-Testset-Paket V3.1-public (21.08. 12:26)** ebenfalls noch Ramona
   (de_01_lead2 = Ramona, Hörprobe bestätigt).
3. **Provenienz fehlt im Dateinamen:** Skripte benennen nur
   `tts_numbers_001.wav` — wer spricht, muss geraten werden (gerade/ungerade).

## Ziel

- **ASR:** Suite-Package v2 aus den aktuellen (sauberen) Quellen bauen +
  installieren → Ramona verschwindet aus dem Benchmark.
- **VAD:** Testset-V4 aus den aktuellen TTS-Quellen neu bauen (Thorsten bleibt,
  Ramona raus — die Quellen sind bereits sauber, nur das Paket ist alt).
- **Provenienz:** Regen-Skripte (vibevoice/piper) + prepare_cv_real +
  build_testset_v3 schreiben/suchen Dateinamen mit Sprecher-Suffix
  (`tts_clean_000_thorsten.wav`, `tts_clean_001_vibevoice_f.wav`) — tolerieren
  alte Namen ohne Suffix (resolve_source/_tts_src). **Umgesetzt.**

## Nicht-Ziel

- Keine Neu-Synthese der TTS-Quellen (die sind bereits Thorsten/VibeVoice).
- Kein Re-Run der Backend-Benchmarks hier (läuft separat auf vast).

## Kontext

- Quellen: `/opt/data/polyschnack-benchmark/benchmark/data/{tts,categories}/`
- Build: `pk-asr/benchmarks/import/build_suite_package.py` (SUITE_VERSION=2)
- VAD-Build: `pk-asr/benchmarks/vad/build_testset_v3.py` (+ assemble_release_zip)
- User-Vorgaben (26.08.): Thorsten OK, nur Ramona raus; NUR Deutsch;
  ASR-Benchmark „relativ gut" → ASR-Set bleibt, nur Quellen aktualisieren.
