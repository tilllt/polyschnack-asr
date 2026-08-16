# ==============================================================
# moonshine-de — CrispASR-Server mit deutschem Spezialmodell
# fidoriel/moonshine-base-de (61.5M, 6.9% WER CV22-de)
# HYBRID (Weg 1): CUDA-Binary mit CPU-Fallback (ggml_backend_init_best)
# GPU-Zugriff NUR via compose.gpu.yml; ohne Overlay läuft CPU.
# LIZENZ: CC-BY-NC-SA-4.0 (nicht-kommerziell!)
# ==============================================================
FROM nvidia/cuda:12.8.0-runtime-ubuntu24.04

ARG CRISPASR_VERSION=v0.8.28

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg ca-certificates wget curl libopenblas0 \
    && rm -rf /var/lib/apt/lists/*

# CrispASR pre-compiled Linux CUDA binary (wie ark-asr/diar/pk-cpp)
# CrispASR pre-compiled binaries — CUDA UND CPU im selben Image (Hybrid):
# Die CUDA-Binary ist hart an libcuda.so.1 gelinkt (DT_NEEDED) und startet
# ohne NVIDIA-Container-Toolkit NICHT (exit 127). /usr/local/bin/crispasr ist
# ein Wrapper, der beim Start wählt: libcuda vorhanden -> CUDA, sonst CPU.
RUN wget -q "https://github.com/CrispStrobe/CrispASR/releases/download/${CRISPASR_VERSION}/crispasr-linux-x86_64-cuda.tar.gz" \
    -O /tmp/crispasr-cuda.tar.gz && \
    tar xzf /tmp/crispasr-cuda.tar.gz -C /tmp && \
    cp /tmp/crispasr-linux-x86_64-cuda/crispasr /usr/local/bin/crispasr-cuda && \
    cp /tmp/crispasr-linux-x86_64-cuda/libc2pa_c.so /usr/local/lib/libc2pa_c.so && \
    rm -rf /tmp/crispasr-cuda.tar.gz /tmp/crispasr-linux-x86_64-cuda && \
    wget -q "https://github.com/CrispStrobe/CrispASR/releases/download/${CRISPASR_VERSION}/crispasr-linux-x86_64.tar.gz" \
    -O /tmp/crispasr-cpu.tar.gz && \
    tar xzf /tmp/crispasr-cpu.tar.gz -C /tmp && \
    cp /tmp/crispasr-linux-x86_64/crispasr /usr/local/bin/crispasr-cpu && \
    rm -rf /tmp/crispasr-cpu.tar.gz /tmp/crispasr-linux-x86_64 && \
    printf '%s\n' \
      '#!/bin/sh' \
      'if ldconfig -p 2>/dev/null | grep -q "libcuda.so.1" || [ -e /usr/lib/x86_64-linux-gnu/libcuda.so.1 ]; then' \
      '  exec /usr/local/bin/crispasr-cuda "$@"' \
      'fi' \
      'echo "[crispasr-hybrid] Keine libcuda.so.1 gefunden - CPU-Backend" >&2' \
      'exec /usr/local/bin/crispasr-cpu "$@"' \
      > /usr/local/bin/crispasr && \
    chmod +x /usr/local/bin/crispasr && \
    ldconfig

# Verify
RUN crispasr --help 2>&1 | head -5

# Model volume — moonshine-de GGUF + tokenizer hier mounten
ENV MOONSHINE_DE_MODEL=/models/moonshine-base-de-fidoriel-q4_k.gguf

# Lizenz-Akzeptanz: fidoriel/moonshine-base-de ist CC-BY-NC-SA-4.0
# (NICHT-kommerziell). Der Server verweigert sonst den Start
# ("Refusing: pass --accept-license cc-by-nc-sa-4.0").
ENV CRISPASR_ACCEPT_LICENSE=cc-by-nc-sa-4.0

# Residenter Post-Prozessor: Interpunktion (fullstop = EN/DE/FR/IT) +
# deutsches Truecasing (lstm, 97,9% F1). Per Env überschreibbar.
ENV CRISPASR_EXTRA_ARGS="--punc-model fullstop --truecase-model lstm"

EXPOSE 5096

CMD ["sh", "-c", "exec crispasr --server -m \"$MOONSHINE_DE_MODEL\" --host 0.0.0.0 --port 5096 $CRISPASR_EXTRA_ARGS"]
