# Tasks — Change 126 (Diarization-Pipeline: globales Speaker-Clustering erzwingen)

- [x] Analyse/Root-Cause (Code-verifiziert): chunk-lokale Labels #292,
      kein diarize_embedder im Request, _normalise_speaker-Lücke,
      keine 1-Speaker-Warnung
- [x] CLI-Referenzmessung: foxnose+WeSpeaker (4 Speaker, 492 Turns) vs.
      pyannote+TitaNet (5 Speaker) vs. Polyschnack-Ist (1 Speaker) —
      erledigt, diarize_local.sh committet
- [x] Fix: `diarize.py` sendet `diarize_embedder` (Config DIARIZE_EMBEDDER,
      Default „auto"; bei foxnose WeSpeaker-Pfad)
- [x] Fix: `config.py` DIARIZE_METHOD-Default → foxnose
- [x] Fix: `_normalise_speaker` — „(speaker N)"/„speaker N"/Zahlen → SPEAKER_0N
- [x] Fix: `_run_diarization` — log.warning bei 1 Speaker und > 10 min Audio
- [x] Deploy-Doku: docs/diarization.md + docs/configuration/env.md
      (Embedder-Env, Container-Anforderung, Symptom-Check)
- [x] Tests: normalise_speaker-Formate, Request-Builder enthält embedder,
      Warnung bei 1 Speaker — 25/25 grün (3 Testdateien)
- [x] Frontend-Regression grün (kein UI-Change; 335/335 von Change 125)
- [ ] Backend-Gesamtsuite grün (läuft: proc_ed0bddef78b7)
- [ ] OpenSpec tasks.md abschließen, Commit, Push, CI
- [ ] Browser/API-Verifikation nach Deploy (User): re-diarize → ≥ 3 Speaker
