# Change 073 — VAD-Samples hörbar auf der Benchmark-Seite

**Status:** in Arbeit · **Datum:** 2026-08-21

## Problem

User (2026-08-21): „Ja ich möchte auch die VAD Samples anhören können.“

Die Benchmark-Seite zeigt nach Change 062/065/071 in der VAD-Sektion nur die
Ergebnistabelle (`VadResultsTable`) — das Testset selbst (235 V3.1-public
Samples: CommonVoice + Piper-Basis, DEMAND-SNR-Mixe, Noise/Musik/Babble-FP)
ist dort **nicht durchstöberbar**. Anders als der ASR-Benchmark gibt es:

1. **Keine öffentliche VAD-Sample-Liste** — `GET /api/benchmark/samples`
   liefert nur ASR-Samples; das VAD-Manifest (`vad-manifest.json`) ist nur
   über den key-geschützten `GET /api/benchmark/vadpackage` (ZIP) erreichbar.
2. **Keine VAD-Audio-Endpoints** — `/audio/{id}` und `/preview/{id}` lösen
   nur ASR-Sample-IDs auf (KeyError → 404); VAD-WAVs liegen unter
   `versions/v{n}/vad/audio/*.wav` und haben keinen Player.

## Ziel

1. **Backend:** Öffentliche VAD-Sample-Liste (`GET /api/benchmark/vadsamples`)
   mit `id`, `source`, `variant`, `gt`-Info und Audio-URLs; WAV- und
   Preview-MP3-Endpoints (`/vadaudio/{id}`, `/vadpreview/{id}`, Preview
   on-demand wie ASR, 128k — iOS-kompatibel).
2. **Frontend:** Die VAD-Sektion zeigt unter der Ergebnistabelle eine
   durchstöberbare Sample-Liste mit WaveformPlayer (MP3-Preview) +
   WAV-Download — gruppiert nach Typ (Basis / DEMAND-SNR-Mix / Noise-FP /
   Musik / Babble / TEN), inkl. Quell-Label (CommonVoice, Piper-TTS, DEMAND).

## Verhaltens-Delta (IST → SOLL)

- **IST:** VAD-Sektion = nur Ergebnistabelle; Samples nicht hörbar.
- **SOLL:** VAD-Sektion = Ergebnistabelle + Testset-Liste mit Playern;
  jede Sample-Zeile abspielbar (Preview) und als WAV ladbar.

## Umsetzung (Skizze)

1. `BenchmarkService.vad_samples()` — liest `vad-manifest.json` (Liste mit
   id/source/variant/split/gt), ergänzt URL-Felder; `vad_audio_path(id)` +
   `ensure_vad_preview(id)` (ffmpeg MP3 128k, gecacht unter
   `versions/v{n}/vad/preview/`).
2. Router: `GET /vadsamples` (öffentlich), `GET /vadaudio/{id}` (WAV),
   `GET /vadpreview/{id}` (MP3) — analog zu `/samples|/audio|/preview`.
3. Frontend: `BenchmarkVadSamples`-Komponente in `BenchmarkPage.tsx`
   (Typ-Gruppierung aus `variant`/`id`, WaveformPlayer mit `preview_url`,
   Download-Link auf `audio_url`); Typ-Labels auf Deutsch.

## Tests / Verifikation

- Backend: `vadsamples` liefert 235 Einträge mit URLs; `vadaudio/{id}` → 200
  WAV; `vadpreview/{id}` → 200 MP3 (on-demand, gecacht); unbekannte ID → 404.
- Frontend: VAD-Sample-Liste rendert Player; WAV-Download-Link vorhanden.
- Gates: pytest-Suite, `npm test`, `tsc --noEmit`, `npm run build`; CI.
- Live: nach Deploy `GET /api/benchmark/vadsamples` → 235; VAD-Sektion auf
  der Seite zeigt Samples mit abspielbaren Playern.
