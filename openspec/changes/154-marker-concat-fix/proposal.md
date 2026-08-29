# Change 154 — Fix: TTS-Marker-Concat bricht ASR (leere Segmente ab 5 min)

**Status:** Proposed (Umsetzung läuft)

## Problem (Produktions-Befund 2026-08-29)

Seit Deploy von Change 147 (TTS-Marker-Vollständigkeits-Erkennung) liefern
alle Transkriptionen **ab 5 min Audiolänge** leere Ergebnisse:
`status=done`, aber `text=''` und `segments=[]` — kein Fehlerpfad, der
Aligner meldet danach „Alignment skipped — word timestamps not verified".

Der Browser war ein roter Hering: Die UI zeigt nur das an, was der Server
persistiert hat — und der persistiert leere Segmente.

## Root Cause (reproduziert auf der ki-box)

`_append_transcript_marker` (service.py) konkateniert das Audio mit dem
Marker-WAV via ffmpeg:

```
-filter_complex "[0:a]aresample=16000,pan=mono[a0];[1:a]aresample=16000,pan=mono[a1];[a0][a1]concat=n=2:v=0:a=1[aout]"
-map [aout] -acodec pcm_s16le -f wav pipe:1
```

Direkter Test gegen `ps-pk-onnx` (127.0.0.1:5092):

- Audio **ohne** Marker → voller Text + Segmente + Wort-Timestamps ✅
- Audio **mit** Marker (dieser Filterkomplex) → `{"text":"","segments":[],"words":[]}` ❌
  (Dauer wird korrekt erkannt: 21,6 s + 8,1 s = 29,7 s — der ONNX-Decoder
  liest die WAV, transkribiert aber nichts)
- Audio mit Marker, aber Filter **nur** `concat=n=2:v=0:a=1[aout]` +
  Output-Flags `-ar 16000 -ac 1` → voller Text ✅

Die `aresample+pan`-Kette im filter_complex erzeugt eine WAV, die der
parakeet-ONNX-Decoder nicht transkribieren kann.

## Fix

`_append_transcript_marker`: filter_complex auf `concat=n=2:v=0:a=1[aout]`
reduzieren; Sample-Rate/Kanäle als Output-Flags (`-ar 16000 -ac 1`)
setzen — ffmpeg konvertiert gemischte Input-Formate (z. B. 44,1 kHz
Stereo-Uploads) automatisch, ohne die kaputte Filterkette.

Bei Inputs mit inkompatiblen Formaten schlägt der concat fehl (rc≠0) →
Fallback wie bisher: Audio unverändert, keine Vollständigkeits-Erkennung,
aber Transkription funktioniert (safe).

## Nicht-Änderung

- Marker-Erkennung/-Stripping (`_strip_transcript_marker`) unverändert
- Queue-/Scheduling-Refactor (Changes 109/110) unverändert — separat
- Frontend-Delivery (Polling stoppt bei done) — separat dokumentiert
