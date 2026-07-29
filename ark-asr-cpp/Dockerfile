# ==============================================================
# CrispASR runtime — downloads pre-compiled release binary
# ==============================================================
FROM nvidia/cuda:12.8.0-runtime-ubuntu24.04

ARG CRISPASR_VERSION=v0.8.24

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg ca-certificates wget unzip \
    && rm -rf /var/lib/apt/lists/*

# Download CrispASR pre-compiled Linux CUDA binary from GitHub release
RUN wget -q "https://github.com/CrispStrobe/CrispASR/releases/download/${CRISPASR_VERSION}/crispasr-linux-x64-cuda.zip" \
    -O /tmp/crispasr.zip && \
    unzip -j /tmp/crispasr.zip "crispasr" -d /usr/local/bin/ && \
    chmod +x /usr/local/bin/crispasr && \
    rm /tmp/crispasr.zip

# Verify
RUN crispasr --help 2>&1 | head -5

# Model volume — mount GGUF files here
RUN mkdir -p /models

# Default entrypoint: just keep crispasr available, use as subprocess
CMD ["crispasr", "--help"]
