# Change 146: Stille ASR-Stream-Abbruche erkennen

**Status:** Accepted

## Problem (User-Befund 2026-08-28)

90-min-Film (8976aa1b…) → nur die ersten 26,6 min transkribiert,
Status trotzdem `done`. Der SSE-Stream des Backends endet bei Problemen
im Audio-Fenster oft ohne error-Event; die Webapp speicherte das
unvollständige Ergebnis still als fertig.

## Diagnose (belegt)

- Recording: duration_s = 5371,9 s (89,5 min), letztes Segment endet
  bei 26,6 min, 45 Segmente, Status done.
- Run 121: Backend ps-pk-onnx, volle Dauer, kein Limit/Offset — der
  Stream brach vorzeitig ab, ohne Fehler zu melden.
- Client-Code (pk_python): `iter_lines()` endet bei Verbindungs-Ende
  ohne Exception → unvollständiges Ergebnis → done.

## Lösung

- `_detect_truncated_asr()`: Wenn das letzte Segment > 30 s vor dem Ende
  des verarbeiteten Audios stoppt → Job wird `failed` mit klarer Meldung
  („Transkription unvollständig: X von Y min — ASR-Verbindung
  abgebrochen"). Der Teil-Text + die Segmente bleiben gespeichert
  (update_result persistiert sie auch bei failed).
- `_probe_audio_duration()`: ffprobe-Fallback für die Dauer des
  verarbeiteten Audios (bei VAD-Trim die getrimmte Dauer).
