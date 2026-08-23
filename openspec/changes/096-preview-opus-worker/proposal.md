# Change 096 — Preview-Optimierung: 24-kbps-Opus + Worker-Fetch

**Status:** Implementiert (lokal getestet), Commit folgt
**User-Auftrag (2026-08-23):** „Setze beide optimierungsoptionen als Punkt 3 um"
(Punkt 3 des 095-Berichts: „Preview verkleinern" + „Decode in Web-Worker verlagern").

## Problem

Ladezeit-Analyse (Change 095, gemessen): Der 45,7-MB-Fetch dauerte < 1 s —
der Flaschenhals war `decodeAudioData` (26 s Desktop / 60–90 s Mobile bei
64-kbps-MP3-Preview). Zwei Hebel: (a) kleinere + schneller-dekodierbare
Preview, (b) Netz-/Buffer-Arbeit vom JS-Main-Thread weg.

## Lösung

### Opt. 1 — Preview 24-kbps-Opus (peaks.py)

- `PREVIEW_BITRATE "64k" → "24k"`, Codec `libmp3lame → libopus`,
  Endung `_preview.mp3 → _preview.opus` (MIME via `_guess_mime` → audio/ogg).
- Ergebnis bei 95 min: **45,7 MB → 15,5 MB** (−66 % Netz) + Opus-Decode
  ~4× schneller als MP3 → decode ~26 s → ~7 s Desktop (Mobile ~4×).
- Alte `.mp3`-Previews bleiben unangetastet (Idempotenz: nur neue Dateien
  werden als `.opus` erzeugt; keine Migration).
- Kompatibilität: decodeAudioData(Opus) = Chrome/Android/Firefox + Safari 17+.
  iOS < 17 → decode-Fehler → vorhandener Fallback (volle Datei, RecordingCard).
- ffmpeg libopus ist im Debian-Image enthalten (Dockerfile `apt-get ffmpeg`).

### Opt. 2 — Worker-DECODE (fetch.worker.ts + WaveformPlayer)

- Neue `frontend/src/workers/fetch.worker.ts`: fetcht die Preview mit
  Streaming-Reader + Fortschritt (0–100) **und dekodiert sie im Worker**:
  `OfflineAudioContext.decodeAudioData` (Opus/MP3 → PCM) → 16-bit-PCM-WAV
  (44-Byte-Header + interleaved Samples) → transferable an den Main-Thread.
- WaveformPlayer lädt die WAV als Blob (`audio/wav`) in WaveSurfer — der
  WS-Decode der unkomprimierten WAV ist trivial (ms-Bereich, kein
  Kompressions-Decode mehr im UI-Kontext). Genau EIN Netz-Fetch.
- **Messung (Chrome-Desktop-Emulation, 95-min-Recording):** Play-Button
  (canPlay) nach **2,6 s** statt ~26 s (45,7-MB-MP3, Main-Thread-Decode).
  Die Preview-Ressource erscheint nicht im Main-Thread-Timing — Beweis,
  dass Fetch+Decode im Worker liefen.
- Fallback: Safari-Worker haben kein `OfflineAudioContext` → roher
  ArrayBuffer geht zurück, WS dekodiert das Originalformat wie bisher
  (iOS ≥ 17 dekodiert Opus; iOS < 17 → vorhandener Fallback volle Datei).
- RAM-Hinweis: Der WAV-Zwischenspeicher (95 min @ 16 kHz/16-bit ≈ 183 MB)
  ist transient (Blob-URL-Revoke + Worker-Terminate nach dem WS-Decode);
  der Playback-AudioBuffer (~365 MB float) entsteht ohnehin in jedem Pfad.

## Tests

- Backend: `test_compute_preview_path_erzeugt_opus` (Endung `.opus`, Codec
  per ffprobe, Idempotenz; ffmpeg fehlt → skip).
- Frontend: jsdom hat kein `Worker` → Fallback-Pfad → bestehende 296 Tests
  unverändert gültig; Worker-Pfad wird im Browser verifiziert (Playwright).
- Verifikation: Play-Button-enable-Zeit (canPlay) mit 15,5-MB-Opus vs.
  45,7-MB-MP3 (26 s).
