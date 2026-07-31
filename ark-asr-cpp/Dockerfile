# ==============================================================
# CrispASR runtime — downloads pre-compiled release binary
# ==============================================================
FROM nvidia/cuda:12.8.0-runtime-ubuntu24.04

ARG CRISPASR_VERSION=v0.8.24

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg ca-certificates wget \
    && rm -rf /var/lib/apt/lists/*

# Download CrispASR pre-compiled Linux CUDA binary from GitHub release
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

# Model volume — mount GGUF files here
RUN mkdir -p /models

# Default entrypoint: just keep crispasr available, use as subprocess
CMD ["crispasr", "--help"]
