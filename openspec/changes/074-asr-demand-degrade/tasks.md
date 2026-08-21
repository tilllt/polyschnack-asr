# Change 074 — Tasks

**Datum:** 2026-08-21 · **Status:** in Arbeit

## T0 Scope-Klärung (User)

- [ ] Flugzeug/Hubschrauber: synthetisch belassen oder andere Quelle?
- [ ] DEMAND-Kategorien: Download (Zenodo) oder nur lokale 2 (Küche/Metro)?
- [ ] Neu-Lauf aller 7 ASR-Backends gegen v3?

## T1 Degrade-Funktion

- [ ] `prepare_cv_real.py`: `_add_demand_snr()` (RMS-Skalierung, SNR 0/5/10 dB,
      GT exakt) — Logik aus `build_testset_v3.py add_snr_variants`.
- [ ] Mapping ASR-Kanal → DEMAND-Quelle (strassenlaerm→DTRAFFIC, auto→DCAR,
      oepnv→DTRAIN/DSTATION/DMETRO, babble→DCAFE/DRESTAURANT — je nach T0).
- [ ] Unittest: Mix-SNR stimmt (RMS-Messung), GT-Regionen unverändert.

## T2 Testset v3 + Release

- [ ] Neues ASR-Testset bauen (v3, deterministisch, gleicher Seed).
- [ ] Release-ZIP + SHA256 + Provenienz (analog VAD v4) auf GitHub
      `tilllt/vad-benchmark-data` (oder ASR-Repo).
- [ ] Webapp: VAD_PACKAGE-/ASR-Manifest-Version auf v3, Seite zeigt v3.

## T3 Neu-Lauf + Submit

- [ ] ASR-Benchmarks (7 Backends × 207 Samples) gegen v3 laufen lassen.
- [ ] Ergebnisse submitten; `/api/benchmark/results` zeigt aktualisierte Zeilen.

## T4 Gates

- [ ] pytest grün, Frontend-Tests grün, CI grün, Live-Verifikation.
