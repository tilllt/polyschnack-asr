# Change 147 — Tasks (TTS-Marker)

## 1. Marker-Asset

- [x] TTS generieren („Seven. Four. Two. …", langsam, mit Pausen)
- [x] Konvertiert zu 16 kHz mono s16 WAV (`webapp/app/transcript_marker.wav`)

## 2. Backend

- [x] `_append_transcript_marker()` — ffmpeg-concat (16k mono) vor der ASR
- [x] `_is_marker_segment()` — Ziffern/Zahlwörter EN/DE/PT
- [x] `_strip_transcript_marker()` — Marker-Segmente entfernen + found-Flag
- [x] Marker fehlt → `failed` mit Meldung (Teil-Text bleibt)

## 3. Verifikation

- [x] 9 Tests (Marker-Erkennung, Entfernung, stille-Abspann-Fall,
      echter ffmpeg-Anhang)
