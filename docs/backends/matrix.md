# Feature-Matrix der Backends

| Feature | ps-pk-onnx | crispr-pk-cpp | crispr-qwen3 | crispr-ark | crispr-moonshine-de | crispr-canary | ps-voxtral* |
|---------|-----------|--------|-----------|---------|-------------|------------|---------|
| Word-Timestamps | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ *nicht trainiert* |
| Live-Streaming (Preview) | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ |
| Async-Jobs (Hintergrund) | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Noise-Reduction (Service) | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| VAD-Trimmung (Silero, extern) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Diarization (CrispASR-diar, extern) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Audio-Enhance (ffmpeg, extern) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Deutsch (Hauptsprache) | ✅ | ✅ | ✅ | ✅ | ✅ (DE-Spezial) | ✅ | ✅ |
| Weitere Sprachen | EN u. a. | EN u. a. | 30 Sprachen | EN u. a. | — | EN/FR/ES | EN |
| Gerät | GPU + CPU | GPU + CPU | GPU + CPU | GPU + CPU | GPU + CPU | GPU + CPU | GPU |
| Modellgröße (Download) | ~2,4 GB | ~0,7 GB | ~3 GB | ~3,2 GB | ~39 MB | ~0,5 GB | ~2,7 GB |

*Voxtral ist **geplant** (Block in `compose.backends.yml` auskommentiert, kein
Image gebaut) — die Zeile zeigt die Zielwerte.*

Die Matrix ist auch live in der GUI (Admin-Bereich → „Modell-Matrix") und via
`GET /api/models/matrix` abrufbar.
