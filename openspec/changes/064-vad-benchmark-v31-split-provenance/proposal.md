# Change 064 — VAD-Benchmark V3.1: Common-Voice-Basis, public/held-out-Split, Provenienz-ZIP

**Status:** in Arbeit · **Datum:** 2026-08-21

## Problem

- Das V3-Testset (Change 063) basiert ausschließlich auf **Piper-TTS-Samples**
  (synthetische Sprache, ein Sprecher). Echte Sprache — Common Voice DE
  (24 akzent-selektierte WAVs, lokal vorhanden aus dem ASR-Benchmark) — fehlt
  als Basis. Für die Produktiv-Realität (Nutzer laden eigene Aufnahmen hoch)
  ist echtes Sprachmaterial mit Mikrofon-/Raumrauschen die realistischere
  VAD-Messung.
- Das Testset liegt als GitHub-Release **ungeschützt komplett öffentlich**.
  Für externe Nutzer ist das gut (Reproduzierbarkeit), aber ohne
  public/held-out-Trennung ist keine ehrliche finale Bewertung möglich:
  sobald ein Testset öffentlich ist, kann es in Trainingsdaten einfließen
  (Leakage) und die Benchmark-Zahlen sind nicht mehr vertrauenswürdig.
- Der Benchmark ist für externe User nicht als Ganzes beziehbar: Es fehlt
  ein ZIP mit Provenienz (je Sample: Quelle, Lizenz, Erzeugungsschritt,
  Seeds), Quellen-Verlinkung und SHA256 — die Daten sind auf GitHub-Release,
  Skripte im Repo, Ergebnisse im Repo verteilt.
- Hinweis User: Das Repo wird von **Harbor** gemirrored
  (`harbor.rand0m.me/public`) — alles, was öffentlich auf GitHub/Images
  landet, ist damit auch dort. Held-out-Samples dürfen daher in **kein**
  öffentliches Artefakt (Git-Repo, Release, ZIP, Container-Image).

## Ziel

1. **Common-Voice-Basis** im V3.1-Testset: die 24 lokalen akzent-selektierten
   CV-DE-WAVs als zweite Basis-Kategorie — pur (Stille-Insertion, GT exakt)
   UND kontaminiert (DEMAND-SNR 0/5/10 dB, GT bleibt exakt, da Speech-Regionen
   deterministisch bekannt).
2. **public/held-out-Split**: deterministischer Split (Seed) in
   `testset.json` (`split: public|heldout`). Nur `public`-Samples landen in
   GitHub-Release/ZIP/Repo/Container-Images. Held-out-Samples existieren
   ausschließlich lokal (`assets/v3-heldout/`, gitignored) und optional auf
   der KI-Box; der Runner lädt sie nie vom Release und weigert sich ohne
   lokales Verzeichnis.
3. **Provenienz-ZIP** (`vad-benchmark-v3.1-public.zip`): public-Samples +
   `testset.json` + `PROVENANCE.md` (Quelle je Sample: Piper-Text-ID /
   Common-Voice-ID, DEMAND-/MUSAN-/TEN-Herkunft, Lizenzen, Seeds,
   Erzeugungs-Skript + Version, SHA256 je Datei) + `results.json` (public-Lauf).
4. Veröffentlichung auf **`tilllt/vad-benchmark-data`** (Release v4):
   ZIP + SHA256 im Release-Body. Kein neues Repo nötig (polyschnack-benchmark
   liegt privat auf GitLab; polyschnack-asr enthält bereits den Benchmark-Code).

## Verhaltens-Delta (IST → SOLL)

- **Builder** (`build_testset_v3.py`): erzeugt zusätzlich CV-basierte Samples
  (pur + SNR) und schreibt `split` je Sample; neue Flags
  `--cv-dir`, `--heldout-dir`, `--split` (generiere nur public/heldout).
  Held-out-Generierung schreibt NIE in Verzeichnisse, die ins Repo/Release
  gehen.
- **Runner** (`run_benchmark.py`): neue Option `--split public|heldout|all`
  (Default `all` für lokale Läufe); `heldout` ohne lokales
  `assets/v3-heldout/` = Abbruch mit Fehlermeldung; Release-Download-Fallback
  liefert nur public. Ergebnisse getrennt: `out/results_v3_public.md/json`,
  `out/results_v3_heldout.md/json`.
- **Release**: v3 (101 TTS-Samples) bleibt als historisches Artefakt; v4
  enthält public-Teil von V3.1 (TTS + CV) als ZIP mit Provenienz.
- **Doku**: README + component-decisions.md mit held-out-Zahlen als
  finale Bewertung, public-Zahlen für externe Reproduzierbarkeit.

## Umsetzung (Skizze)

1. `build_testset_v3.py` erweitern: CV-Basis-Samples einlesen
   (`common_voice/cv_accent_*.wav` + `cv_selection.json`-Metadaten),
   Stille-Insertion + DEMAND-SNR-Varianten analog TTS; deterministischer
   Split 60/40 (Seed 42): public = 60 % der CV-Samples, heldout = 40 % +
   frische TTS-Samples (neue Seeds → andere Insertionen als v3).
2. `run_benchmark.py`: `--split`-Flag + held-out-Guards.
3. ZIP-Assembly + PROVENANCE.md (Generator im Builder oder eigenes Skript).
4. Neubau V3.1, Release v4 (nur public), SHA256.
5. Neulauf public + heldout (7 Engines, Hintergrund).
6. Doku, Commit, Push, CI.

## Referenzen

- Common Voice DE: lokale Selektion `cv_selection.json` (Seed 42, 24
  akzent-WAVs in `common_voice/`), Korpus `cv-corpus.tar.gz` (37 GB),
  Lizenz CC0-1.0 (Mozilla Common Voice)
- DEMAND: Zenodo 1227121 (CC-BY-4.0), MUSAN: `corypaik/musan`
- V3-Baseline: Change 063 (101 Samples, silero F1 0,987 / 0,0 s FP)
