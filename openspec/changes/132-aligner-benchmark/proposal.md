# Change 132: Aligner-Benchmark (Forced-Alignment) in Suite + GUI

## Problem

PolySchnack liefert Karaoke-Wort-Timestamps über den Forced-Aligner
(`aligner-service`, qwen3-forced-aligner). Es gibt keinen öffentlichen,
reproduzierbaren Benchmark, der die Aligner-Qualität ausweist — der
ASR-Benchmark misst nur WER/CER der Transkription, der VAD-Benchmark nur
Sprachaktivität. Ein 3-Wege-Vergleich (qwen3 vs. TADA vs. wav2vec2,
2026-08-26, siehe `docs/`-Notiz + Skill-Referenz `aligner-benchmark-3way.md`)
zeigte große Unterschiede: qwen3 verliert auf 90-s-Clips 62 % der Wörter
(0-Dauer), TADA/wav2vec2 decken 100 % ab — aber das war eine Ad-hoc-Messung
auf 2 Dateien, nicht Teil der Benchmark-Suite.

## Ziel

1. **Aligner-Benchmark auf Basis der beiden deutschen Sample-Quellen**
   (Common-Voice-de echte Stimmen + Piper-TTS), analog zur VAD-Suite:
   eigene Runner-Skripte, Ergebnis-Runs mit `kind="aligner"`, gepoolte
   Metriken im Service (`_aligner_summary`), sichtbar auf `/benchmark`.
2. **GUI erklärt verständlich**, was getestet wird (äquivalent zum
   ASR-Benchmark): Was ist Forced-Alignment? Welche Metriken? Welche
   Aligner? Warum ist es relevant (Karaoke)?

## Metriken (ohne manuelle GT-Zeiten — pragmatisch, dokumentiert)

Für jeden Aligner je Sample (Referenztext = Manifest-Text):

- **Wortabdeckung %**: Anteil der Referenzwörter, die der Aligner mit
  gültiger Zeit liefert (qwen3-Abbruch → niedrig).
- **0-Dauer-Wörter**: Anzahl Wörter mit start == end (Aligner-Fehler).
- **Audio-Abdeckung %**: letztes Wort-Ende / Audio-Dauer (bricht der
  Aligner früh ab?).
- **Kreuz-Δ (ms)**: mittlere |Δ start| zwischen den Alignern je Sample —
  Konsistenz-Indikator (kein absolutes Maß).
- **RTF**: Laufzeit / Audio-Dauer.

Ground-Truth-Wortzeiten (Aligner-SUPERB-WBE) sind für CV nicht verfügbar;
TTS-Samples könnten später per Piper/edge-tts-Wortgrenzen ergänzt werden
(nicht Teil dieses Changes — wird in `docs/benchmark/aligner.md` notiert).

## Umfang

### Backend

- `benchmarks/aligner/` (neu, analog `benchmarks/vad/`):
  - `run_aligner.py` — manifest-Samples (CV + TTS) durch die 3 Aligner
    (qwen3-CLI, CrispASR `--align` TADA, CrispASR `--align-only`
    wav2vec2-xlsr-de), schreibt Runs nach
    `<BENCHMARK_DATA_DIR>/results/runs/aligner_<backend>_*.json`
    (`kind="aligner"`, `manifest_sha256`, `rows`).
  - Modell-Pfade/URLs aus Env (defaults = lokale Modelle, siehe
    `aligner-benchmark-3way.md`-Referenz).
  - README.md mit Aufruf + Metrik-Definition.
- `webapp/app/benchmark_service.py`:
  - `_aligner_summary(runs_dir)` analog `_vad_summary`: poolt
    kind=="aligner"-Runs je Backend → Median/Anteile + `n_samples`.
  - `latest_results()`: `latest["aligner"]` on-the-fly anreichern.
- `webapp/app/routers/benchmark.py`: ggf. Endpunkt für Aligner-Details
  (nur falls nötig — gepoolte Zeile reicht für die GUI zuerst).

### Frontend (`webapp/frontend/src/`)

- `benchmark.ts`: `AlignerResultRow`-Interface + Typ in `BenchmarkResults`.
- `components/BenchmarkPage.tsx`:
  - `AlignerResultsTable` (analog `VadResultsTable`): Tabelle
    (Aligner, n, Wortabdeckung %, 0-Dauer, Audio-Abdeckung %, Kreuz-Δ ms,
    RTF) + **Erklärungsblock** („Was ist Forced-Alignment?" — Warum
    Wort-Zeiten für Karaoke, was wird gemessen, welche Modelle, Hinweis:
    keine manuelle GT → Kreuz-Δ als Konsistenz).
  - Sektion „Forced-Alignment" zwischen VAD und Preisvergleich.
- Tests: `BenchmarkPage.test.tsx` erweitert (Erklärungstext + Tabelle bei
  aligner-Rows), `benchmark.test.ts` (Typ/Parser).

### Doku

- `docs/benchmark/aligner.md` — Methodik, Metriken, Aufruf, Modell-URLs,
  Limitationen (keine WBE-GT; Aligner-SUPERB/PHONDAT als Referenz
  für später).
- `docs/benchmark/index.md` — Verweis auf die Aligner-Sektion.

## Anti-Goals

- Kein Deploy der Aligner als Container (laufen lokal/CLI — wie der
  3-Wege-Vergleich; Containerisierung = eigener Change).
- Keine TADA/wav2vec2-Produktiv-Integration in die Webapp (nur Benchmark).
- Kein manuell gelabeltes GT-Set (Aufwand; später via TTS-Wortgrenzen).

## Nachweis

- Backend: `pytest webapp/tests/` (Benchmark-Service-Tests + Router),
  Aligner-Runner auf 6 Stichproben-Samples (2 je Quelle) ausführbar.
- Frontend: `npm run build` + Vitest (`benchmark.test.ts`,
  `BenchmarkPage.test.tsx`).
- CI grün; keine neuen öffentlichen Daten (Referenztexte bleiben privat).

## Risiken

- qwen3-Abbruch auf langen Clips → Wortabdeckung < 100 % ist ERWARTET
  und wird als Feature der Tabelle sichtbar (nicht als Fehler behandelt).
- Laufzeit der Aligner-Suite (CPU, 3 Aligner × 207 Samples) — Runner
  unterstützt `--limit`/`--category` für Teilläufe; Voll-Lauf später
  als Cron/Manuell.
