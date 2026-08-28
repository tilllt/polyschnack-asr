# Change 146 — Tasks

## 1. Backend-Erkennung

- [x] `service.py`: `_detect_truncated_asr()` (Toleranz 30 s) +
      `_probe_audio_duration()` (ffprobe-Fallback)
- [x] Check nach dem ASR-Ergebnis: Status `failed` + Meldung statt
      stillem `done`; Teil-Text bleibt gespeichert

## 2. Verifikation

- [x] 6 Unit-Tests (u. a. der exakte User-Befund: 26,6 von 89,5 min)
- [ ] Backend-Suite grün
