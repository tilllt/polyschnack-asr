# Tasks — Change 127 (ETA für Rediarize, methoden-getrennt)

- [x] Analyse: ETA nur bei processing; Rediarize-Ingest existiert (Change 115)
- [x] `estimate_diar_eta_s` in `eta.py` (Fallback > gelernt > None, elapsed-Abzug)
- [x] `recordings.py`: ETA-Zweig done + diar_status running (Basis phase_started_at)
- [x] Frontend: ETA-Spanne im bg-diar-Hinweis
- [x] Tests: eta.py (4), Response (1), Frontend (1) — rot → grün
- [x] Proposals finalisiert
- [x] DIAR_RTF-Fallbacks an Benchmark kalibrieren (pyannote 143 s, foxnose 144 s auf 220 s → 0.65; vorher 0.2/0.4 war 3–4× daneben)
- [ ] Backend-Gesamtsuite grün, Frontend-Suite + Build grün
- [ ] Commit, Push, CI
