# Change 073 — Tasks

**Datum:** 2026-08-21 · **Status:** in Arbeit

## T1 Backend: VAD-Sample-Service

- [ ] `BenchmarkService.vad_samples()` — liest `versions/v{n}/vad/vad-manifest.json`,
      liefert `[{id, source, variant, split, has_gt, preview_url, audio_url}]`
      (öffentlich, alle 235 public Samples; held-out ist nicht im Paket).
- [ ] `BenchmarkService.vad_audio_path(id)` — WAV unter `vad/audio/{id}.wav`,
      KeyError bei unbekannter ID.
- [ ] `BenchmarkService.ensure_vad_preview(id)` — ffmpeg MP3 128k mono,
      gecacht unter `vad/preview/{id}.mp3` (on-demand, analog `ensure_preview`).

## T2 Backend: Router-Endpoints

- [ ] `GET /api/benchmark/vadsamples` — öffentlich, Liste aus `vad_samples()`.
- [ ] `GET /api/benchmark/vadaudio/{id}` — FileResponse WAV (analog `/audio`).
- [ ] `GET /api/benchmark/vadpreview/{id}` — FileResponse MP3 (analog `/preview`).
- [ ] Tests: 235 Einträge, URLs gesetzt; Audio 200 + media_type; Preview 200 +
      gecacht (zweiter Aufruf kein ffmpeg); unbekannte ID → 404.

## T3 Frontend: VAD-Sample-Liste mit Player

- [ ] `BenchmarkVadSamples`-Komponente in `BenchmarkPage.tsx` — gruppiert nach
      Typ (Basis / DEMAND-SNR-Mix / Noise-FP / Musik / Babble / TEN), pro Zeile:
      id, Quell-Label (CommonVoice/Piper-TTS/DEMAND), WaveformPlayer
      (preview_url), WAV-Download (audio_url), GT-Hinweis.
- [ ] VAD-Sektion: unter `VadResultsTable` die Sample-Liste einhängen.
- [ ] Tests: Liste rendert Samples + Player; Download-Link auf audio_url.

## T4 Gates & Deploy

- [ ] pytest-Suite grün (GESAMT fail=0), `npm test`, `tsc --noEmit`, build ok.
- [ ] Commit + Push; CI grün.
- [ ] Live-Verifikation: `GET /api/benchmark/vadsamples` → 235; Seite zeigt
      Player; VAD-WAV abspielbar.
