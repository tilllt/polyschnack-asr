# Feature-Matrix der Backends

Quelle: `webapp/app/backends.yaml` → live in der GUI (Admin → „Modell-Matrix")
und via `GET /api/models/matrix`. `external` = Feature kommt aus einem
separaten Service (VAD/Diar), nicht aus dem Backend selbst.

| Feature | ps-pk-onnx | pk-cpp | qwen3 | ark | moonshine-de | canary | voxtral | whisper |
|---------|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| Word-Timestamps | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Live-Streaming (Preview) | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Async-Jobs (Hintergrund) | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Noise-Reduction (Service) | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| VAD-Trimmung (Silero, extern) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Diarization (CrispASR-diar, extern) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Audio-Enhance (ffmpeg, extern) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Native Interpunktion + Truecase | ❌ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Deutsch (Hauptsprache) | ✅ | ✅ | ✅ | ✅ | ✅ (DE-Spezial) | ✅ | ✅ | ✅ |
| Weitere Sprachen | EN u. a. | EN u. a. | 30 Sprachen | EN u. a. | — | EN/FR/ES | EN | multilingual |
| Gerät | GPU + CPU | GPU + CPU | GPU + CPU | GPU + CPU | GPU + CPU | GPU + CPU | GPU + CPU | GPU + CPU |
| Modellgröße (Download) | ~2,4 GB | ~0,7 GB | ~3 GB | ~3,2 GB | ~39 MB | ~0,5 GB | ~5 GB | ~1,8 GB |

Die Spalten ab „pk-cpp" sind CrispASR-Backends: native Interpunktion +
deutsches Truecasing laufen resident im Server (`--punc-model fullstop`,
`--truecase-model lstm`) — dort überspringt die Webapp das LLM-Punctuation
automatisch.

!!! note "Live-Modus"
    Nur `ps-pk-onnx` (und geplante Voxtral-Realtime-Ansätze) unterstützen
    Streaming. Bei anderen Backends wird der ⚡-Toggle ausgeblendet statt
    still ignoriert.
