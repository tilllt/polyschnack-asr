"""Configuration for the optimized PolySchnack v3 service."""
from __future__ import annotations
import logging
import os
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths & model
# ---------------------------------------------------------------------------
ROOT_DIR = Path(__file__).resolve().parent.parent
MODELS_DIR = ROOT_DIR / "models"
MODELS_DIR.mkdir(parents=True, exist_ok=True)

logger = logging.getLogger("polyschnack_v3")


def _getenv(name: str, default: str = "") -> str:
    """Read POLYSCHNACK_<name>, falling back to legacy POLYSNACK_<name> and PARAKEET_<name>.

    The app is called PolySchnack — the environment prefix is POLYSCHNACK_*.
    The legacy POLYSNACK_* and PARAKEET_* prefixes are deprecated (spelling
    aligned with the app name) but kept so existing deployments (compose
    files, systemd units) keep working.
    """
    val = os.getenv(f"POLYSCHNACK_{name}")
    if val is not None:
        return val
    legacy = os.getenv(f"POLYSNACK_{name}")
    if legacy is not None:
        logger.warning("POLYSNACK_%s is deprecated — use POLYSCHNACK_%s", name, name)
        return legacy
    legacy2 = os.getenv(f"PARAKEET_{name}")
    if legacy2 is not None:
        logger.warning("PARAKEET_%s is deprecated — use POLYSCHNACK_%s", name, name)
        return legacy2
    return default

# Point HF cache at local models dir
os.environ.setdefault("HF_HOME", str(MODELS_DIR))
os.environ.setdefault("HF_HUB_CACHE", str(MODELS_DIR))
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "true")

MODEL_CONFIGS = {
    "parakeet-tdt-0.6b-v3": {
        "hf_id": "nemo-parakeet-tdt-0.6b-v3",
        "quantization": "int8",
        "description": "INT8 CPU profile",
    },
    "istupakov/parakeet-tdt-0.6b-v3-onnx": {
        "hf_id": "istupakov/parakeet-tdt-0.6b-v3-onnx",
        "quantization": None,
        "description": "FP32 GPU default profile",
    },
    "grikdotnet/parakeet-tdt-0.6b-fp16": {
        "hf_id": "grikdotnet/parakeet-tdt-0.6b-fp16",
        "quantization": "fp16",
        "description": "FP16",
    },
}
GPU_DEFAULT_MODEL = "istupakov/parakeet-tdt-0.6b-v3-onnx"
CPU_DEFAULT_MODEL = "parakeet-tdt-0.6b-v3"


def _auto_select_model() -> str:
    """Detect GPU and pick the best model, falling back to CPU INT8."""
    try:
        import onnxruntime as ort
        providers = ort.get_available_providers()
        has_cuda = "CUDAExecutionProvider" in providers
        if not has_cuda:
            logger.info("Auto-select: no CUDA → CPU INT8 model")
            return CPU_DEFAULT_MODEL

        # Try to read GPU name
        gpu_name = ""
        try:
            import subprocess
            out = subprocess.run(
                ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
                capture_output=True, text=True, timeout=5,
            )
            if out.returncode == 0 and out.stdout.strip():
                gpu_name = out.stdout.strip().lower()
        except Exception:
            pass

        # Pick model based on GPU class
        if "a100" in gpu_name or "h100" in gpu_name or "a10" in gpu_name or "l40" in gpu_name:
            logger.info("Auto-select: enterprise GPU (%s) → FP16 model", gpu_name[:40])
            return "grikdotnet/parakeet-tdt-0.6b-fp16"
        logger.info("Auto-select: CUDA GPU (%s) → FP32 model", gpu_name[:40] if gpu_name else "unknown")
        return GPU_DEFAULT_MODEL  # istupakov/parakeet-tdt-0.6b-v3-onnx
    except Exception as exc:
        logger.info("Auto-select: detection failed (%s) → CPU INT8 model", exc)
        return CPU_DEFAULT_MODEL


_DEFAULT_MODEL_ENV = _getenv("DEFAULT_MODEL", "").lower()
if _DEFAULT_MODEL_ENV in MODEL_CONFIGS:
    DEFAULT_MODEL = _DEFAULT_MODEL_ENV
elif _DEFAULT_MODEL_ENV in {k.lower() for k in MODEL_CONFIGS}:
    # Resolve to canonical casing
    DEFAULT_MODEL = {k.lower(): k for k in MODEL_CONFIGS}[_DEFAULT_MODEL_ENV]
else:
    DEFAULT_MODEL = _auto_select_model()


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
TARGET_SR = 16_000

# Long-audio chunking: sliding window with overlap (achetronic-style).
# Each window covers CHUNK_SECONDS and shares CHUNK_OVERLAP_SECONDS with its
# neighbours; the shared overlap gives the encoder context and is split at a
# silence boundary (VAD -> mel-energy -> midpoint cascade), see chunker.py.
CHUNK_SECONDS = float(_getenv("CHUNK_SECONDS", "300"))
CHUNK_OVERLAP_SECONDS = float(_getenv("CHUNK_OVERLAP_SECONDS", "15"))

# VAD parameters (Silero)
VAD_THRESHOLD = float(_getenv("VAD_THRESHOLD", "0.5"))
VAD_MIN_SILENCE_MS = int(_getenv("VAD_MIN_SILENCE_MS", "400"))
VAD_SPEECH_PAD_MS = int(_getenv("VAD_SPEECH_PAD_MS", "120"))

# Providers
USE_GPU = _getenv("USE_GPU", "true").lower()  # auto|true|false
GPU_DEVICE_ID = int(_getenv("GPU_DEVICE_ID", "0"))

# Micro-batch worker. The default is the validated RTX 3090 GPU profile;
# CPU deployments should set POLYSCHNACK_BATCHED=0 and POLYSCHNACK_USE_GPU=false.
MAX_BATCH_SIZE = int(_getenv("MAX_BATCH_SIZE", "4"))
BATCH_WINDOW_MS = float(_getenv("BATCH_WINDOW_MS", "4"))

# Noise reduction (spectral gating)
NOISE_REDUCE = _getenv("NOISE_REDUCE", "true").lower() in ("true", "1", "yes")


def _get_env_int(name: str, default: int, minimum: int = 1) -> int:
    try:
        return max(minimum, int(_getenv(name, str(default))))
    except (TypeError, ValueError):
        return max(minimum, default)


# ORT threading (CPU)
import os as _os
try:
    _available_logical = len(_os.sched_getaffinity(0))
except (AttributeError, OSError):
    _available_logical = _os.cpu_count() or 1

try:
    import psutil  # type: ignore
    _physical = psutil.cpu_count(logical=False) or _available_logical
except Exception:
    _physical = _available_logical

DEFAULT_INTRA = 1 if USE_GPU != "false" else min(_physical, _available_logical)
ORT_INTRA_THREADS = _get_env_int("ORT_INTRA_THREADS", DEFAULT_INTRA)
ORT_INTER_THREADS = _get_env_int("ORT_INTER_THREADS", 1)

# Audio preprocessing pool
AUDIO_WORKERS = _get_env_int("AUDIO_WORKERS", min(8, _physical))

# Keep numeric libs from creating competing thread pools
for _e in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS",
           "NUMEXPR_NUM_THREADS", "VECLIB_MAXIMUM_THREADS"):
    os.environ.setdefault(_e, "1")

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s  %(levelname)-7s  %(name)s: %(message)s",
    stream=sys.stdout,
    force=True,
)

CPU_INFO = {
    "physical": _physical,
    "logical": _available_logical,
    "ort_intra": ORT_INTRA_THREADS,
    "ort_inter": ORT_INTER_THREADS,
    "audio_workers": AUDIO_WORKERS,
}
