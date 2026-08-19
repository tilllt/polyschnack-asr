# Engineering

## ADDED Requirements

### Requirement: FQS-Referenzvergleich für ASR-Backends

- **Geltungsbereich:** ASR-Evidenz im PolySchnack-Projekt
  (Change 021, „Evidenzbasierte Komponentenwahl").
- **Ablauf:** Der PolySchnack-Benchmark (Repo `polyschnack-benchmark`)
  enthält das öffentliche FQS-Testmaterial (Zenodo 10209813 + Supplement-
  Tabellen 5/6 der Studie Wollin-Giering et al. 2024) als Subset `fqs`
  mit 4 Samples (2 DE, 2 EN) inkl. Ground-Truth (manuelle Referenztranskripte).
- **Messung:** Eigene Backends werden auf den FQS-Ausschnitten mit dem
  Standard-Benchmark gemessen (WER/CER/RTF); die WER der kommerziellen
  Anbieter (Amberscript, Dragon, F4x, Happy Scribe, NVivo, Otter, Sonix,
  Trint, Whisper) werden aus den publizierten Tabellen-Transkripten auf
  **denselben Ausschnitten** berechnet.
- **Kennzeichnung:** Ergebnisse externer Herkunft sind im Report und im
  Decision-Log als solche markiert („externe Daten, Tools von 2022,
  identisches Audio"); publizierte Interviewwerte der Studie (volle
  5-Minuten-Interviews) dürfen nicht mit Ausschnitt-Werten vermischt werden.
- **Pflicht-Dokumentation:** Ergebnis und Quellen werden in
  `docs/component-decisions.md` (Abschnitt ASR) eingetragen.

#### Scenario: FQS-Vergleichslauf

- **Akteure:** Entwickler, Benchmark-Repo.
- **Eingaben:** `python benchmark run` mit FQS-Subset; fqs_tables.json
  (Tool-Transkripte) + ground_truth.json.
- **Ergebnis:** Report-Sektion „FQS-Referenzvergleich" mit WER je eigenem
  Backend und je kommerziellem Anbieter auf identischem Audio; Eintrag im
  Decision-Log mit Quellen.

#### Scenario: Neue Backend-Entscheidung

- **Akteure:** Entwickler, Reviewer.
- **Eingaben:** Kandidatenentscheidung mit ASR-Benchmark-Ergebnis.
- **Ergebnis:** Entscheidung berücksichtigt die FQS-Referenz (eigene
  Backends vs. kommerzielle Anbieter) und ist im Decision-Log mit Quellen
  nachvollziehbar; ohne Kennzeichnung externer Daten wird sie abgelehnt.
