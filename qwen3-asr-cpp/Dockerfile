# ==============================================================
# Builder stage — compile qwen3-asr.cpp with CUDA support
# HYBRID (Weg 1): CUDA-Build enthält CPU-Backend via
# ggml_backend_init_best — GPU via compose.gpu.yml, sonst CPU.
# ==============================================================
FROM nvidia/cuda:12.8.0-devel-ubuntu24.04 AS builder

ARG DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
    git cmake build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /src
RUN git clone --recursive https://github.com/predict-woo/qwen3-asr.cpp.git .
RUN cmake -B build -DCMAKE_BUILD_TYPE=Release && \
    cmake --build build -j$(nproc)
# Shared libraries EINSAMMELN (im Builder!): Upstream linkt Server+CLI
# dynamisch gegen libqwen3-asr.so UND die ggml-Familie (libggml.so.0,
# libggml-base.so.0, libggml-cpu.so.0 …) — sie liegen verstreut im
# Build-Output (ggml-Submodule). Die Runtime-Stage hat KEIN /src/build;
# deshalb hier bündeln und per COPY übernehmen (Regression 2026-08-14:
# find lief in der Runtime-Stage ins Leere → „erfolgreicher" Build ohne Lib).
RUN mkdir -p /src/libs && find /src/build -name '*.so*' -exec cp -a {} /src/libs/ \;

# ==============================================================
# Runtime stage
# ==============================================================
FROM nvidia/cuda:12.8.0-runtime-ubuntu24.04

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg ca-certificates wget \
    && rm -rf /var/lib/apt/lists/*

# Copy both binaries — server for HTTP, CLI for forced alignment
COPY --from=builder /src/build/qwen3-asr-server /usr/local/bin/
COPY --from=builder /src/build/qwen3-asr-cli /usr/local/bin/

# Shared libraries aus der Builder-Stage übernehmen (dort gebündelt in
# /src/libs; die Runtime-Stage hat kein /src/build — siehe Builder oben).
COPY --from=builder /src/libs/ /usr/local/lib/
RUN ldconfig

# GGUF model volume — mount ASR + ForcedAligner here
RUN mkdir -p /models

# Default: run the server.
# The CLI is available as "qwen3-asr-cli" for the adapter's subprocess calls.
EXPOSE 5094
ENTRYPOINT ["qwen3-asr-server"]
CMD ["-m", "/models/qwen3-asr-0.6b-q8_0.gguf", \
     "--host", "0.0.0.0", \
     "--port", "5094", \
     "--convert", \
     "--max-upload-mb", "1024", \
     "-t", "8"]
