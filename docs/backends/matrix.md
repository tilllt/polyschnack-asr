# Feature-Matrix der Backends

| Feature | ps-pk-onnx | crispr-pk-cpp | crispr-qwen3 | crispr-ark | crispr-moonshine-de | crispr-canary |
|---------|-----------|--------|-----------|---------|-------------|------------|
| Word-Timestamps | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Live-Streaming (Preview) | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Async-Jobs (Hintergrund) | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Noise-Reduction (Service) | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| VAD-Trimmung (Silero, extern) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Diarization (CrispASR-diar, extern) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Audio-Enhance (ffmpeg, extern) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Deutsch (Hauptsprache) | ✅ | ✅ | ✅ | ✅ | ✅ (DE-Spezial) | ✅ |
| Weitere Sprachen | EN u. a. | EN u. a. | 30 Sprachen | EN u. a. | — | EN/FR/ES |
| Gerät | GPU + CPU | GPU + CPU | GPU + CPU | GPU + CPU | GPU + CPU | GPU + CPU |
| Modellgröße (Download) | ~2,4 GB | ~0,7 GB | ~3 GB | ~3,2 GB | ~39 MB | ~0,5 GB |

Die Matrix ist auch live in der GUI (Admin-Bereich → „Modell-Matrix") und via
`GET /api/models/matrix` abrufbar.
