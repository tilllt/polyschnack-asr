# Change 064 — Tasks

## 1. Builder-Erweiterung (`benchmarks/vad/build_testset_v3.py`)

- [x] CV-Basis einlesen: `common_voice/cv_accent_*.wav` (24 Stück) +
      Metadaten aus `cv_selection.json` (text, accent, gender)
- [x] CV-Samples auf 16 kHz mono normalisieren (ffmpeg), Lautstärke-Check
      (kein leeres/verzerrtes Audio)
- [x] CV-Varianten analog TTS: Stille-Insertion (lead2/trail2/both2, mid1 bei
      ≥ 4 s) + DEMAND-SNR 0/5/10 dB × 2 Quellen — exakte GT je Variante
- [x] Deterministischer Split (Seed 42): 60 % public / 40 % heldout je
      Kategorie; heldout zusätzlich: frische TTS-Samples mit neuen
      Insertion-Seeds (nicht identisch mit v3)
- [x] `split`-Feld je Sample in `testset.json`; Ausgabe public nach
      `assets/v3/`, heldout nach `assets/v3-heldout/` (nur lokal)
- [x] Flags: `--cv-dir`, `--heldout-dir`, `--split public|heldout|all`
- [x] Repro-Check: zweiter Lauf → identische SHA256 der WAVs
      (gzip-mtime=0-Fix nötig, danach deterministisch)

## 2. Runner (`benchmarks/vad/run_benchmark.py`)

- [x] `--split public|heldout|all` (Default `all`)
- [x] Guard: `heldout` ohne `assets/v3-heldout/` → Abbruch mit Fehler
- [x] Release-Download-Fallback liefert NUR public (heldout nie vom Release)
- [x] Ergebnisse getrennt: `out/results_v3_public.md/json` +
      `out/results_v3_heldout.md/json`

## 3. Provenienz-ZIP

- [x] Generator (`assemble_release_zip.py`): `vad-benchmark-v3.1-public.zip` =
      public-WAVs + `testset.json` + `PROVENANCE.md` + `results_v3_public.json`
- [x] `PROVENANCE.md`: je Sample Quelle (Piper-ID/CV-ID), Lizenz, Seeds,
      Erzeugungsschritt; DEMAND/MUSAN/TEN-Herkunft + Lizenzen; SHA256 je Datei
      (SHA256SUMS im ZIP)
- [x] Kein held-out-Sample im ZIP (Guard im Generator)

## 4. Release

- [x] GitHub-Release v4 auf `tilllt/vad-benchmark-data`: ZIP + SHA256 im Body
      (Download verifiziert: SHA256 identisch)
- [x] README `benchmarks/vad/`: v4-Link, Download, held-out-Policy (warum
      heldout nicht öffentlich)

## 5. Benchmark-Läufe

- [x] Lokaler Lauf public (235, 7 Engines) + heldout (126, 7 Engines)
- [x] Ergebnis: silero public F1 0,995 / heldout 0,998, 0,0 s FP —
      hält auf CV

## 6. Doku & Abschluss

- [x] `docs/component-decisions.md`: V3.1-Zahlen (public vs heldout),
      CV-Erkenntnis, held-out-Policy
- [x] OpenSpec 063 archivieren (abgeschlossen)
- [ ] Commit (Change 064 + Archivierung 063) + Push + CI prüfen
