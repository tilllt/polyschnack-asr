"""Unit-Tests für die Energie-basierte Wortgrenzen-Korrektur (2026-08-17).

Hintergrund: qwen3-forced-aligner liefert für Wörter in künstlich langen
Pausen 0-Dauer-Intervalle (start==end). _resolve_zero_duration füllt dann
end = nächster start → die KOMPLETTE Stille wird dem Wort zugeschlagen
(Karaoke-Markierung bleibt viel zu lange aktiv). _energy_refine ordnet die
Wörter den akustisch belegten Regionen zu.

Lauf: python3 -m unittest tests/test_aligner_energy.py -v  (im aligner-service/)
"""
import json
import os
import struct
import sys
import tempfile
import unittest
import wave

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from aligner_server import _energy_refine, _resolve_zero_duration  # noqa: E402


def _make_wav(path: str, words_s: list, pause_s: float = 0.35,
              tone_hz: int = 440, sr: int = 16000, amp: int = 8000) -> float:
    """Synthetisches 16-kHz-Mono-WAV: pro 'Wort' einen Ton der Dauer
    word_s, getrennt durch pause_s Stille. Liefert die Gesamtdauer."""
    frames = bytearray()
    import math

    def add_silence(sec: float) -> None:
        nonlocal frames
        n = int(sec * sr)
        for _ in range(n):
            frames += struct.pack("<h", 0)

    def add_tone(sec: float) -> None:
        nonlocal frames
        n = int(sec * sr)
        for i in range(n):
            v = int(amp * math.sin(2 * math.pi * tone_hz * i / sr))
            frames += struct.pack("<h", v)

    total = 0.0
    for ws in words_s:
        add_silence(pause_s)
        add_tone(ws)
        total += pause_s + ws
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(bytes(frames))
    return total


class TestEnergyRefine(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp(prefix="align-energytest-")
        self.wav = os.path.join(self.tmp, "synth.wav")
        # Wörter bei 0.35, 1.05, 1.75, 2.45 (je 0.35 Stille + 0.35 Ton)
        _make_wav(self.wav, [0.35] * 4)

    def tearDown(self) -> None:
        for f in os.listdir(self.tmp):
            os.unlink(os.path.join(self.tmp, f))
        os.rmdir(self.tmp)

    def test_zero_duration_pulled_to_region(self):
        """0-Dauer-Wort, dessen Start an der Vorgänger-Grenze klebt (=
        Lücken-Anfang), wird in die nächste akustische Region gezogen."""
        # Töne: 0.35–0.70 | 1.05–1.40 | 1.75–2.10 | 2.45–2.80
        # Start 0.70 klebt am Ende von Ton 1 → gehört zu Ton 2 (1.05–1.40)
        words = [
            {"word": "A", "start": 0.70, "end": 0.70},
            {"word": "B", "start": 1.75, "end": 1.75},
        ]
        out = _energy_refine(words, self.wav)
        self.assertAlmostEqual(out[0]["start"], 1.05, delta=0.05)
        self.assertAlmostEqual(out[0]["end"], 1.40, delta=0.05)
        self.assertAlmostEqual(out[1]["start"], 1.75, delta=0.05)
        self.assertAlmostEqual(out[1]["end"], 2.10, delta=0.05)

    def test_valid_boundary_unchanged(self):
        """CLI-Grenze mitten in einer akustischen Region bleibt erhalten."""
        words = [{"word": "A", "start": 0.50, "end": 0.60}]
        out = _energy_refine(words, self.wav)
        self.assertAlmostEqual(out[0]["start"], 0.50, delta=0.02)
        self.assertAlmostEqual(out[0]["end"], 0.60, delta=0.02)

    def test_end_capped_at_region(self):
        """CLI-Ende jenseits der Region (in der Stille) wird auf das
        Region-Ende gezogen — die Pause gehört keinem Wort."""
        words = [{"word": "A", "start": 0.50, "end": 2.50}]
        out = _energy_refine(words, self.wav)
        self.assertAlmostEqual(out[0]["end"], 0.70, delta=0.05)

    def test_missing_wav_returns_unchanged(self):
        words = [{"word": "A", "start": 0.1, "end": 0.2}]
        out = _energy_refine(words, os.path.join(self.tmp, "gibtsnicht.wav"))
        self.assertEqual(out, words)

    def test_empty_words_returns_empty(self):
        self.assertEqual(_energy_refine([], self.wav), [])

    def test_full_pipeline_with_resolve(self):
        """Gesamtkette wie im Handler: resolve=False → refine → resolve."""
        words = [
            {"word": "A", "start": 0.35, "end": 0.35},
            {"word": "B", "start": 1.05, "end": 1.05},
            {"word": "C", "start": 1.75, "end": 1.75},
            {"word": "D", "start": 2.45, "end": 2.45},
        ]
        out = _resolve_zero_duration(_energy_refine(words, self.wav))
        self.assertEqual(len(out), 4)
        # Reihenfolge: Starts monoton steigend, keine Überlappung
        for i in range(1, len(out)):
            self.assertGreaterEqual(out[i]["start"], out[i - 1]["end"] - 1e-6)
        # Alle Intervalle gültig
        for w in out:
            self.assertGreater(w["end"], w["start"])


if __name__ == "__main__":
    unittest.main()
