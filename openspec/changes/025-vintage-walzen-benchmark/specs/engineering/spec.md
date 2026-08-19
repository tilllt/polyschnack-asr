# Engineering Spec — Delta für Change 025

## ADDED Requirements

### REQ-BENCH-026: Historische deutsche Aufnahmen als Benchmark-Kategorien
`Benchmark-Datensatz` · `must`

Der PolySchnack-Benchmark enthält zusätzlich zu den synthetischen
Kategorien echte historische deutsche Aufnahmen:

- **`vintage_walzen`** (33 Samples): gesprochene Phonographenwalzen
  1898–1914 (Quelle wachston.de), keine künstliche Degradation.
- **`zwirner_dialekt`** (geplant): Dialekt-Tonbandaufnahmen 1955–1970
  (Zwirner-Korpus, DGD/IDS Mannheim) — nur nach Klärung der
  Nutzungsbedingungen; ohne Freigabe werden keine Audio-/Transkript-
  Dateien ins Repo übernommen.

### REQ-BENCH-027: Ground-Truth-Workflow für Quellen ohne Transkript
`Benchmark-Datensatz` · `must`

Für Quellen ohne offizielles Transkript (Wachston) gilt:

1. Vortranskription mit einem dokumentierten Referenzmodell
   (faster-whisper large-v3, `language=de`, `initial_prompt`) in
   `hypotheses_<modell>.json`.
2. Manuelle Korrektur durch die Projektleitung; Übernahme in
   `ground_truth.json` mit Provenienz je Sample: `reference`, `source`,
   `language`, `confidence` (hoch/mittel/niedrig), `corrected_by`.
3. Samples mit `confidence: niedrig` fließen nicht in
   Kategorie-Mittelwerte ein, sondern werden nur einzeln geführt.

### REQ-BENCH-028: Ehrliche Messung historischer Robustheit
`Benchmark-Auswertung` · `must`

- Historische Kategorien werden **ohne Degradation** gemessen
  (Originalmaterial ist bereits „vintage").
- Hohe WER auf Walzenqualität (Bandbreite ~100 Hz–5 kHz) sind erwartbar
  und werden **nicht geglättet** (Anti-Gaming-Prinzip).
- Ergebnisse fließen in Report, `docs/component-decisions.md` und
  Businessplan (Kapitel 3.4) ein; Zwirner-Korpus-Ergebnisse werden bis
  zur Lizenzklärung als „nicht veröffentlicht, Lizenzprüfung offen"
  markiert.
