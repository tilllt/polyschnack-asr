# Change 025 — Design

## Datenquellen

| Quelle | Material | Transkript | Lizenz/Zugang | Status |
|---|---|---|---|---|
| wachston.de („Deutschsprachige humoristische Szenen…") | 33 MP3, gesprochenes Deutsch, 1898–1914 (Walzen: 100 Hz–5 kHz, Knistern), ~76 min gesamt | Keine — Ground Truth via Vortranskription + Korrektur | Audio frei abrufbar; private Sammlung | Download ✅, Vortranskription läuft |
| DGD / IDS Mannheim, Korpus „Deutsche Mundarten" (Zwirner-Korpus) | ~570 Tonbandaufnahmen deutscher Dialekte, 1955–1970, BRD+DDR, je ~20 min | Orthographisch/phonetisch in DGD | Registrierung (Forschung/Lehre); kommerzielle Nutzung klären | Zugang beantragen, Lizenz prüfen |

## Ground-Truth-Workflow (Wachston, kein offizielles Transkript)

1. **Vortranskription:** faster-whisper `large-v3` (EU vast-Instanz,
   RTX 3060/4070, ~0,05–0,10 $) je MP3, `language=de`, `initial_prompt`
   („historische Phonographenwalze, um 1900, Berliner Dialekt,
   humoristische Szene") → `hypotheses_whisper.json` (Text + Segmente).
2. **Korrektur durch Projektleitung:** User korrigiert die Texte direkt in
   `hypotheses_whisper.json` (oder als `corrections_<user>.json`-Overlay);
   Segmente bleiben für spätere Forced-Alignment-Referenzen erhalten.
3. **Review/Übernahme:** Hermes überführt die Korrekturen in
   `ground_truth.json` (Schema analog FQS): je Sample `reference`,
   `source`, `language`, `confidence` (hoch/mittel/niedrig) und
   `corrected_by`.
4. **Manifest/prepare:** Samples als Kategorie `vintage_walzen` (keine
   Degradation, `source: vintage_walzen`).

## Kategorien-Definition

- `vintage_walzen` (33 Samples): echte Phonographenwalzen, gesprochenes
  Deutsch, 1898–1914. Erwartung: WER deutlich über Studio-/TTS-Werten —
  misst Robustheit auf historischem Material.
- `zwirner_dialekt` (geplant, ~10–20 Samples): Dialekt-Tonband 1955–1970,
  nur nach Lizenzklärung; falls nicht lizenzierbar, wird die Kategorie
  ohne Audio-Dateien als „interne Messung" geführt.

## Messung

- Bestehende Suite (`backend_benchmark_full.py --categories vintage_walzen,
  --result-suffix _walzen`) auf frischer vast-Instanz je Backend,
  Ergebnisse unter `results/result_benchmark_<backend>_walzen.json`.
- Report: neue Kategorien erscheinen automatisch in den Kategorie-Tabellen;
  kein neues Report-Feature nötig.
- Decision-Log-Eintrag + Businessplan 3.4 (Robustheit auf historischem
  Material) nach Abschluss.

## Einschränkungen

- GT-Korrektur ist subjektiv bei unverständlichen Passagen → `confidence`
  je Sample; Samples mit `confidence: niedrig` werden nicht in
  Kategorie-Mittelwerte einbezogen, nur einzeln geführt.
- Walzen-Tonhöhenschwankungen erschweren auch die manuelle Korrektur
  (Referenztext kann von der „korrekten" Schriftform abweichen).
- Zwirner-Korpus: Dialekte (nicht Standarddeutsch) — WER-Messung mit
  Standard-Referenz ist nur ein Näherungsmaß; ggf. `cer` zusätzlich.
