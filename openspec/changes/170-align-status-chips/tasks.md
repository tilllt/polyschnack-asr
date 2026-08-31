# Change 170 — Tasks

- [x] Befund: align/rediarize setzen keine progress_note/phase_started_at
      → Chips zeigen Alt-Zustand („finalizing läuft seit 180m").
- [x] align-Worker: set_progress(rec_id, 1, "alignment") nach running.
- [x] rediarize-Worker: set_progress(rec_id, 1, "diarization") (ersetzt
      „Re-Diarize läuft …").
- [x] openspec/change 170 committen, push main, CI grün.
- [ ] Deploy; Live-Test: „New word timestamps" → Chip „aligning" blinkt,
      Zeit-Anzeige ab Job-Start.
