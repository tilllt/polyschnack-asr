# ==============================================================
# canary-asr — CrispASR-Server mit NVIDIA canary-1b-v2
# Multilingual (EN/DE/FR/ES) mit expliziter Sprachsteuerung, ~600 MB
# HYBRID (Weg 1): CUDA-Binary mit CPU-Fallback (ggml_backend_init_best)
# GPU-Zugriff NUR via compose.gpu.yml; ohne Overlay läuft CPU.
# LIZENZ: CC-BY-4.0
# ==============================================================
FROM nvidia/cuda:12.8.0-runtime-ubuntu24.04

ARG CRISPASR_VERSION=v0.8.25

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg ca-certificates wget curl \
    && rm -rf /var/lib/apt/lists/*

# CrispASR pre-compiled Linux CUDA binary (wie ark-asr/diar/pk-cpp)
RUN wget -q "https://github.com/CrispStrobe/CrispASR/releases/download/${CRISPASR_VERSION}/crispasr-linux-x86_64-cuda.tar.gz" \
    -O /tmp/crispasr.tar.gz && \
    tar xzf /tmp/crispasr.tar.gz -C /tmp && \
    cp /tmp/crispasr-linux-x86_64-cuda/crispasr /usr/local/bin/crispasr && \
    cp /tmp/crispasr-linux-x86_64-cuda/libc2pa_c.so /usr/local/lib/libc2pa_c.so && \
    ldconfig && \
    chmod +x /usr/local/bin/crispasr && \
    rm -rf /tmp/crispasr.tar.gz /tmp/crispasr-linux-x86_64-cuda

# Verify
RUN crispasr --help 2>&1 | head -5

# Model volume — canary GGUF hier mounten
ENV CANARY_ASR_MODEL=/models/canary-1b-v2-q4_k.gguf

# Residenter Post-Prozessor: Interpunktion (fullstop = EN/DE/FR/IT) +
# deutsches Truecasing (lstm, 97,9% F1). Per Env überschreibbar.
ENV CRISPASR_EXTRA_ARGS="--punc-model fullstop --truecase-model lstm"

EXPOSE 5097

CMD ["sh", "-c", "exec crispasr --server -m \"$CANARY_ASR_MODEL\" --host 0.0.0.0 --port 5097 $CRISPASR_EXTRA_ARGS"]
