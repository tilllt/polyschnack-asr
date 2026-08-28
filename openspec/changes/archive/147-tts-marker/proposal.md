# Change 147: TTS-Marker für deterministische Vollständigkeits-Erkennung

**Status:** Accepted

## Problem

Change 146 (VAD-Schätzung) wurde von Till korrekt als unbrauchbar
zurückgewiesen: Filme können in den letzten 30 s oder Minuten keine
Dialoge haben (stiller Abspann) — eine Zeit-Toleranz erzeugt falsche
Alarme. 

## Lösung (User-Idee)

Ein einmalig generierter TTS-Marker (eindeutige Ziffernfolge
„7 4 2 8 1 6 0 3 9", langsames Tempo mit Pausen) wird ans Audio-Ende
gehängt. Transkribiert die ASR den Marker, hat sie das Audio-Ende
erreicht (vollständig); fehlt er, brach der Stream ab → ehrlich `failed`.
Deterministisch, kein Raten — stille Abspänne sind automatisch korrekt.

## Änderungen

- `webapp/app/transcript_marker.wav`: vorab generierter Marker (8 s,
  16 kHz mono) — liegt im Image (`COPY app ./app`).
- `service.py`: `_append_transcript_marker()` (ffmpeg-concat auf
  16 kHz mono WAV), `_is_marker_segment()` (Ziffern/Zahlwörter
  EN/DE/PT, ≥ 4 Treffer & ≥ 50 % der Tokens), `_strip_transcript_marker()`
  (entfernt Marker-Segmente, liefert found-Flag).
- Marker-Erkennung nach der ASR: fehlt der Marker → `failed` mit
  Meldung (Teil-Text bleibt gespeichert). Change-146-Logik ersetzt.
- Backends ohne Compressed-Support bekommen ohnehin 16k-WAV — der
  Marker-Anhang erzeugt daraus die ASR-Eingabe in einem ffmpeg-Lauf.
