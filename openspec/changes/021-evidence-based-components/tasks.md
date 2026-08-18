# Tasks — Change 021: Evidenzbasierte Komponentenwahl

## Phase 1 — Grundlagen
- [ ] Decision-Log anlegen: `docs/component-decisions.md` im Repo
      (Format: Komponente · Kandidaten · Metriken/Ergebnis · Entscheidung
      · Quellen · Datum)
- [ ] Bestandsaufnahme: je Komponente aktueller Stand + offene Frage
      (ASR, Diar, Aligner, TTS, Backends) in den Log eintragen

## Phase 2 — Offene Entscheidungen (aus 2026-08)
- [ ] **Aligner-Benchmark:** deutsche Testaufnahme (30–60 min,
      500–1.000 manuell geprüfte Wortgrenzen), Metriken WBE/UBE
      (Aligner-SUPERB-Formeln) + RTF; Kandidaten: Qwen3-ForcedAligner
      (f16 + q4-k-m, CPU + CUDA) vs. MFA (german_mfa v3.0.0) vs.
      WhisperX; Seamless nur als Referenz (CC-BY-NC = Ausschluss);
      Ergebnis + Quellen in den Decision-Log
- [ ] **Diar-Entscheidung eintragen:** CPU > GPU belegt (PR
      CrispStrobe/CrispASR#364, Messzahlen) — in den Decision-Log
      übernehmen
- [ ] **ASR-Evidenz:** bestehende WER-Messung (polyschnack-benchmark)
      um Lizenz-Check je Backend ergänzen; aktuelle Kandidaten-Liste
      im Log
- [ ] **Remote-Backends:** Preis-/Mess-Evidenz aus Change 020
      (vast/theta/EU-only) in den Decision-Log nachführen

## Phase 3 — Prozess verankern
- [ ] Re-Evaluation-Regel in CONTRIBUTING.md / Docs dokumentieren
      (neuer Kandidat/Release → gleiche Testaufnahme → Log-Update)
