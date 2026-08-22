# Tasks — Change 082

- [ ] T1: `webapp/app/eta.py` — RTF-Tabellen + `estimate_eta_s()`
- [ ] T2: `Recording.processing_started_at` + `set_processing` setzt es
- [ ] T3: `service.py`: `rec.backend` beim Job-Start zurückschreiben
- [ ] T4: `_recording_to_dict`: eta_total_s/eta_low_s/eta_high_s +
      processing_started_at (iso_utc) bei processing
- [ ] T5: Backend-Tests (`test_eta.py`, set_processing, Dict-Felder)
- [ ] T6: Frontend: `heartbeatState.level` (Ampel) + Live-Zähler +
      Phasen-Chip-Dauer
- [ ] T7: Frontend: `etaFromRate`/`updateEta` entfernen, `fmtEtaRange` +
      ETA-Zeile aus Backend-Feldern
- [ ] T8: i18n de/en/pt + Frontend-Tests
- [ ] T9: Vollsuite, Commit, Push, CI-Watch
