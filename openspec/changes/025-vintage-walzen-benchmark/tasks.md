# Change 025 — Tasks

## Phase 1: Daten beschaffen
- [x] Wachston-Walzen: 33 gesprochene deutsche MP3s geladen
      (`benchmark/data/vintage_walzen/audio/`, 54 MB, ~76 min)
- [ ] Zwirner-Korpus: DGD-Registrierung beantragen, Nutzungsbedingungen
      (kommerzielle Nutzung) mit DGD-Support klären, Korpus-Details
      (Anzahl/Dauer/Transkriptionsart) nach Registrierung verifizieren
- [ ] Bei Freigabe: 10–20 repräsentative Dialekt-Aufnahmen auswählen

## Phase 2: Ground Truth (Wachston)
- [x] Vortranskription faster-whisper large-v3 auf vast-Instanz
      (EU, Auto-Destroy) → `hypotheses_whisper.json`
- [ ] Vortranskripte dem User zur Korrektur übergeben
- [ ] Korrekturen reviewen und in `ground_truth.json` übernehmen
      (Schema: reference, source, language, confidence, corrected_by)
- [ ] `prepare.py`: Kategorie `vintage_walzen` integrieren (keine Degradation)

## Phase 3: Messung + Doku
- [ ] Backend-Messung aller Backends (`--categories vintage_walzen`) auf
      frischer vast-Instanz je Backend, Ergebnisse in `results/`
- [ ] Report prüfen (neue Kategorien in Tabellen)
- [ ] `docs/component-decisions.md`: ASR-Eintrag „Robustheit auf
      historischem Material" mit realen Werten
- [ ] Businessplan 3.4 ergänzen (echte Vintage-Werte, Lizenzhinweis
      Zwirner)
- [ ] Commit + Push (benchmark-Repo + pk-asr), CI prüfen
