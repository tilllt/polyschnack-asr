# Aligner-Benchmark (Forced-Alignment)

Vergleicht die Forced-Aligner, die PolySchnack für Karaoke-Wort-Timestamps
einsetzen kann — auf den **beiden deutschen Sample-Quellen** des
Benchmark-Sets (Common-Voice-de echte Stimmen + Piper-TTS).

## Aligner

| Aligner | Typ | Modell | Hinweis |
|---------|-----|--------|---------|
| `qwen3` | Forced-Aligner (CTC, ggml) | `cstr/qwen3-forced-aligner-0.6b-GGUF` (q8_0, ~986 MB; mit Mel-Tensoren) | Produktiver PolySchnack-Aligner; bricht auf langen Clips ab (0-Dauer-Wörter) |
| `tada` | TADA-Aligner (CrispASR `--align`) | `cstr/tada-tts-1b-GGUF` + Codec + Encoder + `tada-aligner-de.gguf` (de nur im 3b-Repo!) | Multilingual, voice-ref-basiert; langsamster (CPU) |
| `wav2vec2` | CTC (CrispASR `--align-only`) | `wav2vec2-large-xlsr-53-german-q4_k.gguf` | Klassisches CTC, schnell, vollständige Abdeckung |

Details + Pitfalls: Skill-Referenz `aligner-benchmark-3way.md` (multi-backend-asr).

## Aufruf

```bash
# HTTP-Modus (Default, Change 133): gegen den aligner-Container
ALIGN_URL=http://127.0.0.1:5099 python3 run_aligner.py --data-dir <BENCHMARK_DATA_DIR> \
    [--mode http] [--sources cv,tts] [--limit N] [--category X] [--skip qwen3]

# Lokal-Modus (Dev-Box ohne Container)
python3 run_aligner.py --data-dir <BENCHMARK_DATA_DIR> --mode local \
    [--sources cv,tts] [--limit N] [--category X] [--skip qwen3]
```

- `<BENCHMARK_DATA_DIR>` = Verzeichnis mit `versions/v1/manifest.json` +
  `results/` (gleiches Layout wie der ASR/VAD-Benchmark).
- **HTTP-Modus (Change 133)**: spricht `POST /v1/audio/align` des
  aligner-Containers an (`file`/`text`/`lang`/`method`) — derselbe Pfad,
  den die Webapp nutzt. Der Container läuft mit CrispASR als einziger
  Binary für alle 3 Methoden (`method=qwen3|tada|wav2vec2`).
- Schreibt je Aligner `results/runs/aligner_<algo>_<ts>.json`
  (`kind="aligner"`, `manifest_sha256`) + Kreuz-Vergleich
  `aligner_cross_<ts>.json` (`kind="aligner_cross"`, paarweises
  |Δ start|-Median).
- Die Webapp zeigt die gepoolten Zeilen automatisch unter
  `/benchmark` → Sektion „Forced-Aligner" (Service reichert
  `latest.json` on-the-fly an, kein Neustart nötig).

HTTP-Modus: `ALIGN_URL` (Default `http://127.0.0.1:5099`),
`ALIGNER_TIMEOUT_S` (Default 600).

Lokal-Modus: Modell-/Binary-Pfade per Env: `QWEN3_ASR_CLI`,
`QWEN3_ALIGNER_MODEL`, `CRISPASR_BIN`, `TADA_MODEL`, `TADA_CODEC`,
`TADA_ALIGNER_DE`, `WAV2VEC2_MODEL`.

## Metriken (je Sample)

- **Wortabdeckung %**: Anteil der Referenzwörter mit gültiger Zeit
  (start < end). qwen3 < 100 % ist erwartet (Abbruch auf langen Clips).
- **0-Dauer-Wörter**: Wörter mit start == end (Aligner-Fehler).
- **Audio-Abdeckung %**: letztes Wort-Ende / Audio-Dauer.
- **RTF**: Laufzeit / Audio-Dauer.
- **Kreuz-Δ (ms)**: median |Δ start| zwischen je zwei Alignern
  (index-weise, nur übereinstimmende Wörter) — Konsistenz-Indikator,
  kein absolutes Qualitätsmaß.

## Limitationen

- Keine manuell gelabelten Ground-Truth-Wortzeiten (Aligner-SUPERB-WBE).
  CV hat keine GT; TTS-Wortgrenzen könnten später ergänzt werden.
  Referenz-Benchmarks: Aligner-SUPERB (TIMIT), FA-Bench, PHONDAT/MAUS (de).
- HTTP-Modus braucht den aligner-Container (Change 133, CrispASR-Basis);
  ohne Container `--mode local` (CPU, langsam — TADA ~3× RT auf 90 s).
- Referenztexte und Samples bleiben privat (Anti-Gaming): Nur die
  gepoolten Metrik-Zeilen gehen in die öffentliche GUI, nie Texte/Audio.
