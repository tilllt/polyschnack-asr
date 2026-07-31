"""Generate synthetic speech fixtures for benchmarking the PolySchnack ASR server.

Usage:
    uv run python scripts/gen_test_audio.py [--force]

Outputs (relative to repo root = polyschnack-asr/):
    tests/audio/short_10s.wav    ~10 s, 16 kHz mono PCM s16le
    tests/audio/short_10s.txt    reference transcript
    tests/audio/medium_60s.wav   ~60 s, 16 kHz mono PCM s16le
    tests/audio/medium_60s.txt   reference transcript
    tests/audio/long_30min.wav   ~30 min, 16 kHz mono PCM s16le
    tests/audio/long_30min.txt   reference transcript

Requirements: network access (gTTS calls Google TTS API).
Audio is decoded from MP3 -> PCM using miniaudio (pure Python wheel, no ffmpeg).
"""

from __future__ import annotations

import argparse
import io
import struct
import wave
from pathlib import Path
from typing import List, Tuple

import miniaudio
import numpy as np
from gtts import gTTS

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
SAMPLE_RATE = 16_000
CHANNELS = 1
SAMPLE_WIDTH = 2  # s16le = 2 bytes

# Repo root is two levels up from this file (approach-a/scripts/gen_test_audio.py)
REPO_ROOT = Path(__file__).resolve().parents[2]
AUDIO_DIR = REPO_ROOT / "tests" / "audio"

# Fixed deterministic sentences.
SENTENCES_SHORT: List[str] = [
    "The quick brown fox jumps over the lazy dog.",
    "Speech recognition technology has advanced rapidly in recent years.",
    "Neural networks can now transcribe audio with remarkable accuracy.",
]

SENTENCES_MEDIUM: List[str] = [
    "Automatic speech recognition is the process of converting spoken language into text.",
    "Modern ASR systems use deep learning models trained on thousands of hours of audio data.",
    "The Parakeet model from NVIDIA achieves state of the art performance on multiple benchmarks.",
    "Real time transcription enables new applications in accessibility, customer service, and productivity.",
    "Low latency inference is critical for interactive voice applications.",
    "Quantized models reduce memory requirements while maintaining high transcription quality.",
    "The ONNX runtime provides optimized execution across different hardware platforms.",
    "Edge deployment allows speech recognition to run without internet connectivity.",
    "Streaming transcription produces partial results as the user speaks.",
    "Word error rate is the standard metric used to evaluate speech recognition accuracy.",
]

SENTENCES_PARAGRAPH: List[str] = [
    "The history of artificial intelligence spans more than seven decades.",
    "Early computers were programmed with explicit rules to perform tasks.",
    "The advent of machine learning changed how computers learn from data.",
    "Deep neural networks can automatically extract features from raw inputs.",
    "Convolutional neural networks revolutionized image classification tasks.",
    "Recurrent networks enabled sequence modeling for speech and language.",
    "The transformer architecture introduced the attention mechanism in two thousand seventeen.",
    "Large language models can generate coherent text on almost any topic.",
    "Multimodal models combine vision, language, and audio understanding.",
    "Researchers continue to push the boundaries of what artificial intelligence can accomplish.",
    "Speech recognition is one of the oldest problems in artificial intelligence research.",
    "Early systems relied on hand crafted features and hidden Markov models.",
    "End to end deep learning replaced the traditional pipeline with a single neural network.",
    "Connectionist temporal classification loss enabled training without aligned labels.",
    "The attention mechanism allows models to focus on relevant parts of the input sequence.",
    "Transfer learning lets pre-trained models be fine-tuned on smaller datasets.",
    "Self-supervised learning reduces the need for large amounts of labeled data.",
    "Data augmentation techniques improve model robustness to recording conditions.",
    "Noise robustness is essential for deployment in real world environments.",
    "Speaker adaptation improves accuracy for individual users over time.",
]


# ---------------------------------------------------------------------------
# Audio helpers
# ---------------------------------------------------------------------------
def gtts_to_mp3_bytes(text: str, lang: str = "en") -> bytes:
    """Synthesize text to speech and return raw MP3 bytes."""
    buf = io.BytesIO()
    tts = gTTS(text=text, lang=lang, slow=False)
    tts.write_to_fp(buf)
    return buf.getvalue()


def mp3_bytes_to_pcm_f32(mp3_data: bytes) -> np.ndarray:
    """Decode MP3 bytes to float32 PCM samples at their native sample rate.

    Returns (samples_f32, sample_rate).
    """
    decoded = miniaudio.decode(
        mp3_data,
        nchannels=CHANNELS,
        sample_rate=SAMPLE_RATE,  # let miniaudio resample to target rate
        output_format=miniaudio.SampleFormat.FLOAT32,
    )
    samples = np.frombuffer(decoded.samples, dtype=np.float32).copy()
    return samples, decoded.sample_rate


def resample_f32(samples: np.ndarray, src_rate: int, dst_rate: int) -> np.ndarray:
    """Simple linear interpolation resample from src_rate to dst_rate."""
    if src_rate == dst_rate:
        return samples
    ratio = dst_rate / src_rate
    new_length = int(len(samples) * ratio)
    if new_length == 0:
        return np.zeros(0, dtype=np.float32)
    old_indices = np.arange(len(samples), dtype=np.float64)
    new_indices = np.linspace(0, len(samples) - 1, new_length, dtype=np.float64)
    return np.interp(new_indices, old_indices, samples).astype(np.float32)


def f32_to_s16le(samples: np.ndarray) -> bytes:
    """Convert float32 [-1, 1] PCM to signed 16-bit little-endian bytes."""
    clipped = np.clip(samples, -1.0, 1.0)
    s16 = (clipped * 32767.0).astype(np.int16)
    return s16.tobytes()


def sentences_to_pcm(sentences: List[str]) -> Tuple[bytes, int]:
    """Synthesize a list of sentences and return (pcm_s16le_bytes, num_samples)."""
    all_pcm: List[np.ndarray] = []
    for sentence in sentences:
        mp3_data = gtts_to_mp3_bytes(sentence)
        f32_samples, src_rate = mp3_bytes_to_pcm_f32(mp3_data)
        resampled = resample_f32(f32_samples, src_rate, SAMPLE_RATE)
        all_pcm.append(resampled)
        # Small silence gap (0.3 s) between sentences
        silence = np.zeros(int(0.3 * SAMPLE_RATE), dtype=np.float32)
        all_pcm.append(silence)

    combined = np.concatenate(all_pcm, axis=0)
    return f32_to_s16le(combined), len(combined)


def write_wav(path: Path, pcm_bytes: bytes) -> None:
    """Write raw s16le PCM bytes to a WAV file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(SAMPLE_WIDTH)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(pcm_bytes)


def read_wav_num_frames(path: Path) -> int:
    with wave.open(str(path), "rb") as wf:
        return wf.getnframes()


def duration_seconds(path: Path) -> float:
    with wave.open(str(path), "rb") as wf:
        return wf.getnframes() / wf.getframerate()


# ---------------------------------------------------------------------------
# Fixture generators
# ---------------------------------------------------------------------------
def generate_short(force: bool = False) -> None:
    wav_path = AUDIO_DIR / "short_10s.wav"
    txt_path = AUDIO_DIR / "short_10s.txt"
    if wav_path.exists() and not force:
        print(f"[skip] {wav_path} already exists (use --force to regenerate)")
        return

    print("[gen ] Generating short_10s (~10 s) ...")
    sentences = SENTENCES_SHORT
    pcm, _ = sentences_to_pcm(sentences)
    write_wav(wav_path, pcm)
    txt_path.write_text(" ".join(sentences), encoding="utf-8")
    dur = duration_seconds(wav_path)
    print(f"       -> {wav_path}  ({dur:.1f}s, {wav_path.stat().st_size / 1024:.0f} KB)")


def generate_medium(force: bool = False) -> None:
    wav_path = AUDIO_DIR / "medium_60s.wav"
    txt_path = AUDIO_DIR / "medium_60s.txt"
    if wav_path.exists() and not force:
        print(f"[skip] {wav_path} already exists (use --force to regenerate)")
        return

    print("[gen ] Generating medium_60s (~60 s) ...")
    sentences = SENTENCES_MEDIUM
    pcm, _ = sentences_to_pcm(sentences)
    write_wav(wav_path, pcm)
    txt_path.write_text(" ".join(sentences), encoding="utf-8")
    dur = duration_seconds(wav_path)
    print(f"       -> {wav_path}  ({dur:.1f}s, {wav_path.stat().st_size / 1024:.0f} KB)")


def generate_long(force: bool = False) -> None:
    """Generate ~30 min audio by looping SENTENCES_PARAGRAPH until target duration."""
    wav_path = AUDIO_DIR / "long_30min.wav"
    txt_path = AUDIO_DIR / "long_30min.txt"
    if wav_path.exists() and not force:
        print(f"[skip] {wav_path} already exists (use --force to regenerate)")
        return

    target_seconds = 30 * 60  # 30 minutes
    print(f"[gen ] Generating long_30min (~{target_seconds}s = 30 min) ...")
    print("       This synthesizes one paragraph, then loops the PCM — fast.")

    # Synthesize the paragraph once
    pcm_bytes, num_samples = sentences_to_pcm(SENTENCES_PARAGRAPH)
    paragraph_duration = num_samples / SAMPLE_RATE
    print(f"       Paragraph duration: {paragraph_duration:.1f}s")

    # How many repetitions do we need?
    repetitions = max(1, int(np.ceil(target_seconds / paragraph_duration)))
    # Expand PCM by repeating (memory-efficient: keep as bytes, concat)
    full_pcm = pcm_bytes * repetitions

    # Trim to exactly target_seconds worth of samples
    target_samples = target_seconds * SAMPLE_RATE
    target_bytes = target_samples * SAMPLE_WIDTH
    full_pcm = full_pcm[:target_bytes]

    write_wav(wav_path, full_pcm)

    # Reference transcript: repeat the paragraph text as many times
    paragraph_text = " ".join(SENTENCES_PARAGRAPH)
    full_text = (" " + paragraph_text) * repetitions
    full_text = full_text.strip()
    txt_path.write_text(full_text, encoding="utf-8")

    dur = duration_seconds(wav_path)
    print(f"       -> {wav_path}  ({dur:.1f}s, {wav_path.stat().st_size / 1024 / 1024:.1f} MB)")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate synthetic WAV fixtures for PolySchnack ASR benchmarks."
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Regenerate files even if they already exist.",
    )
    parser.add_argument(
        "--only",
        choices=["short", "medium", "long"],
        help="Generate only one fixture instead of all three.",
    )
    args = parser.parse_args()

    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Output directory: {AUDIO_DIR}")

    if args.only == "short":
        generate_short(args.force)
    elif args.only == "medium":
        generate_medium(args.force)
    elif args.only == "long":
        generate_long(args.force)
    else:
        generate_short(args.force)
        generate_medium(args.force)
        generate_long(args.force)

    print("\nDone.")


if __name__ == "__main__":
    main()
