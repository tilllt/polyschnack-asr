# Tasks — Change 024: FQS-Referenzvergleich

## Phase 1 — Benchmark-Repo: Daten & Extraktion
- [ ] `benchmark/scripts/fqs_download.py`: Zenodo-`Appendix 2 - Sound files.zip`
      (File-URL gepinnt) herunterladen, SHA-256 je MP3 verifizieren (Hashes
      im Skript), nach `benchmark/data/fqs/audio/` entpacken; Idempotent
      (überspringt vorhandene, verifizierte Dateien).
- [ ] `benchmark/scripts/fqs_extract_tables.py`: Transkript-Extraktion aus
      tab5/tab6.pdf (Design: Header-Bänder, Block-x0-Spaltengrenze,
      Schlangen-Layout) → `benchmark/data/fqs/fqs_tables.json`
      (je Tool, je Beispiel: Text; inkl. `Manual`).
- [ ] `benchmark/data/fqs/ground_truth.json`: Manual-Texte je Beispiel +
      Quellenangaben (DOI, Tabellen-URLs, Extraktionsdatum).
- [ ] Extraktions-Skript + Ground Truth gegen die Lesereihenfolge des PDFs
      verifizieren (Validierungs-Test).

## Phase 2 — Benchmark-Repo: Manifest & Report
- [ ] Manifest um 4 Samples erweitern: `fqs_de_1`, `fqs_de_2`, `fqs_en_1`,
      `fqs_en_2` (source=fqs, Kategorien `fqs_de`/`fqs_en`, audio_path →
      data/fqs/audio, Referenztext = Manual).
- [ ] `run.py`: MIME-Type je Dateiendung (wav → audio/wav, mp3 → audio/mpeg)
      — bisher hart auf `audio/wav`; FQS-Samples sind MP3.
- [ ] `report.py`: Sektion **„FQS-Referenzvergleich"**:
      - Tabelle A: eigene Backends (WER/CER/RTF) auf den 4 Samples (aus
        results.jsonl, Kategorie fqs_*).
      - Tabelle B: kommerzielle Anbieter-WER auf denselben Ausschnitten
        (aus fqs_tables.json + ground_truth, jiwer) — markiert „externe
        Daten, Tools 2022, identisches Audio", inkl. Hinweis-Box
        (Ausschnitte ≠ volle Interviews; keine statistische Aussage).
      - Verweis auf external_fqs.json (publizierte Interviewwerte) bleibt
        bestehen, klar getrennt.
- [ ] `benchmark/tests/test_fqs.py`: Ground-Truth-Integrität, Manifest-
      Einträge, Extraktions-Validierung (Manual-Texte), Report-Rendering.

## Phase 3 — Testlauf (Nacht-Suite-Muster)
- [ ] Wrapper für 4 Backends (`ps-pk-onnx`, `crispr-pk-cpp`,
      `crispr-moonshine-de`, `crispr-canary`) auf vast.ai (EU, CUDA ≥ 12.8,
      1 Instanz je Backend, Destroy im finally + Cleanup + Watchdog-Cron).
- [ ] FQS-Samples + (optional) Retry qwen3/ark dokumentiert.
- [ ] Ergebnisse in `benchmark/results/results.jsonl` (WER/CER/RTF),
      Report generieren und prüfen.

## Phase 4 — Entscheidung & Doku
- [ ] `docs/component-decisions.md` (pk-asr): Abschnitt „ASR —
      FQS-Referenzvergleich" mit Ergebnistabelle (eigene Backends vs.
      kommerzielle Anbieter auf identischem Audio), Quellen, Datum,
      Einordnung.
- [ ] Businessplan Kapitel 3.4 um die real gemessene Vergleichstabelle
      ergänzen (ersetzt/ergänzt die FQS-Fremdwerte), PDF regenerieren,
      an tilllt@yahoo.com senden.
- [ ] README (Benchmark-Repo): FQS-Subset dokumentieren (Datenherkunft,
      Einschränkungen, Nutzung).
- [ ] Commit + Push beide Repos (pk-asr: Change 024; benchmark: Daten/
      Skripte/Report), CI prüfen und melden.
