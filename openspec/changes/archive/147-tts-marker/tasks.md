# Change 147 — Tasks (TTS-Marker + Chunk-Erkennung)

## 1. Vollständigkeits-Erkennung (primär: Chunk-Zählung)

- [x] `pk_python.py`: Stream liefert `chunked`/`truncated`/
      `chunks_received`/`chunks_total` (letzter `chunk_index` vs. `total_chunks`)
- [x] `service.py`: `truncated` → `failed` mit „X von Y Chunks"-Meldung

## 2. TTS-Marker (Fallback für Backends ohne Chunk-Zählung)

- [x] TTS generieren („Seven. Four. Two. …", langsam, mit Pausen)
- [x] Konvertiert zu 16 kHz mono s16 WAV (`webapp/app/transcript_marker.wav`)

## 2. Backend

- [x] `_append_transcript_marker()` — ffmpeg-concat (16k mono) vor der ASR
- [x] `_is_marker_segment()` — Ziffern/Zahlwörter EN/DE/PT
- [x] `_strip_transcript_marker()` — Marker-Segmente entfernen + found-Flag
- [x] Marker fehlt → `failed` mit Meldung (Teil-Text bleibt)

## 3. Progress-Bar (aussagekräftiger)

- [x] `service.py` `_on_chunk`: note `"asr Chunk X/Y"` (statt nur `"asr"`)
- [x] `RecordingCard.tsx`: `activePhaseIndex` akzeptiert `asr …`;
      `phaseDetail` zeigt „Chunk X/Y" (wie alignment-Details)

- [x] 9 Tests (Marker-Erkennung, Entfernung, stille-Abspann-Fall,
      echter ffmpeg-Anhang)
