# Engineering-Spec — Change 029

## REQ-WEB-037 — Backend-Option `crispr-voxtral` (CrispASR voxtral4b)

1. Das Image `polyschnack-asr-voxtral` (CrispASR v0.8.29, Hybrid
   CUDA/CPU) wird per CI-Job `build-voxtral` auf Harbor gepusht und über
   `mirror-ghcr` nach ghcr.io/tilllt gespiegelt.
2. Der Container startet `crispasr --server --backend voxtral4b -m
   "$VOXTRAL_ASR_MODEL"` auf Port 5100; das Modell (Default
   `Voxtral-Mini-4B-Realtime-2602-Q8_0.gguf`) wird über
   `backends.yaml model_files` ausgeliefert und unter `./DATA/models`
   gemountet.
3. `backends.yaml` registriert `crispr-voxtral` mit Adapter
   `CrispAsrHttpClient`; Compose-Profil `crispr-voxtral`; Health unter
   `/health`; Sprachen de/en; Geräte gpu+cpu.

## REQ-WEB-038 — Backend-Option `crispr-whisper` (CrispASR whisper)

1. Das Image `polyschnack-asr-whisper-crisp` (CrispASR v0.8.29, Hybrid
   CUDA/CPU) wird per CI-Job `build-whisper-crisp` auf Harbor gepusht und
   über `mirror-ghcr` nach ghcr.io/tilllt gespiegelt.
2. Der Container startet `crispasr --server --backend whisper -m
   "$WHISPER_ASR_MODEL"` auf Port 5101; das Modell (Default
   `ggml-large-v3-turbo-q5_0.bin`) wird über `backends.yaml model_files`
   ausgeliefert und unter `./DATA/models` gemountet.
3. `backends.yaml` registriert `crispr-whisper` mit Adapter
   `CrispAsrHttpClient`; Compose-Profil `crispr-whisper`; Health unter
   `/health`; Sprachen de/en; Geräte gpu+cpu.
