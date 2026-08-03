"""Device-Auto-Detect für die pyannote-Diarization (Task A3, Hybrid).

Die Pipeline soll auf GPU laufen, wenn der Container GPU-Zugriff hat
(torch.cuda.is_available() → True, gesetzt via compose.gpu.yml runtime:
nvidia), sonst auf CPU. Ein CUDA-Fehler beim Laden (OOM, Treiber) muss
transparent auf CPU zurückfallen statt die Aufnahme zu killen.
"""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _reset_pipeline(monkeypatch):
    """Pipeline-Cache je Test zurücksetzen."""
    import app.diarize as d

    monkeypatch.setattr(d, "_pipeline", None)
    monkeypatch.setattr(d, "_pipeline_device", None)
    yield


class FakePipeline:
    def __init__(self, device=None):
        self.device = device
        self.calls = []

    def __call__(self, audio_path, **kwargs):
        self.calls.append((audio_path, kwargs))
        return self


def _patch_loader(monkeypatch, device_seen):
    """Ersetzt _load_pipeline_impl durch einen Fake, der das Device festhält."""
    import app.diarize as d

    def fake_impl(device, *, token):
        device_seen.append(device)
        return FakePipeline(device=device)

    monkeypatch.setattr(d, "_load_pipeline_impl", fake_impl)


class _FakeCuda:
    @staticmethod
    def is_available():
        return True


class _FakeTorch:
    cuda = _FakeCuda()


def _set_device(monkeypatch, device: str):
    """Erzwingt das Device-Ergebnis (mockt _detect_device)."""
    import app.diarize as d

    monkeypatch.setattr(d, "_detect_device", lambda: device)


def test_device_cuda_when_available(monkeypatch):
    import app.diarize as d

    _set_device(monkeypatch, "cuda")
    monkeypatch.setenv("HF_TOKEN", "hf_test")
    seen = []
    _patch_loader(monkeypatch, seen)

    pipe = d._load_pipeline()
    assert seen == ["cuda"]
    assert pipe.device == "cuda"


def test_device_cpu_when_unavailable(monkeypatch):
    import app.diarize as d

    _set_device(monkeypatch, "cpu")
    monkeypatch.setenv("HF_TOKEN", "hf_test")
    seen = []
    _patch_loader(monkeypatch, seen)

    d._load_pipeline()
    assert seen == ["cpu"]


def test_cuda_load_failure_falls_back_to_cpu(monkeypatch):
    """CUDA-Load wirft (z. B. OOM) → zweiter Versuch mit device='cpu'."""
    import app.diarize as d

    _set_device(monkeypatch, "cuda")
    monkeypatch.setenv("HF_TOKEN", "hf_test")

    attempts = []

    def flaky_impl(device, *, token):
        attempts.append(device)
        if device == "cuda":
            raise RuntimeError("CUDA out of memory")
        return FakePipeline(device=device)

    monkeypatch.setattr(d, "_load_pipeline_impl", flaky_impl)

    pipe = d._load_pipeline()
    assert attempts == ["cuda", "cpu"]
    assert pipe.device == "cpu"


def test_no_token_still_raises_before_device_probe(monkeypatch):
    """Ohne HF_TOKEN kein Device-Probe — Fehler kommt sofort (no-token)."""
    import app.diarize as d

    monkeypatch.delenv("HF_TOKEN", raising=False)
    _set_device(monkeypatch, "cuda")

    with pytest.raises(d.DiarizationError) as ei:
        d._load_pipeline()
    assert ei.value.code == "no-token"


def test_diarize_uses_pipeline_with_kwargs(monkeypatch):
    """diarize() reicht num_speakers/min_duration_off an die Pipeline weiter."""
    import app.diarize as d

    _set_device(monkeypatch, "cpu")
    monkeypatch.setenv("HF_TOKEN", "hf_test")
    seen = []
    _patch_loader(monkeypatch, seen)

    fake = FakePipeline()
    monkeypatch.setattr(d, "_load_pipeline_impl", lambda device, *, token: fake)

    segs = d.diarize("/tmp/x.wav", num_speakers=2, min_duration_off=0.3)
    assert fake.calls[0][1] == {"min_speakers": 2, "max_speakers": 2, "min_duration_off": 0.3}
    assert isinstance(segs, list)


def test_detect_device_cuda_when_torch_available(monkeypatch):
    """_detect_device: echtes torch-Fake mit cuda.is_available()=True → cuda."""
    import sys
    import app.diarize as d

    fake_torch = _FakeTorch()
    monkeypatch.setitem(sys.modules, "torch", fake_torch)
    # _detect_device importiert torch frisch aus sys.modules
    assert d._detect_device() == "cuda"


def test_detect_device_cpu_without_torch(monkeypatch):
    """_detect_device: kein torch importierbar → cpu (nie ein Crash)."""
    import builtins
    import app.diarize as d

    real_import = builtins.__import__

    def fake_import(name, *a, **kw):
        if name == "torch":
            raise ImportError("no torch")
        return real_import(name, *a, **kw)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    assert d._detect_device() == "cpu"
