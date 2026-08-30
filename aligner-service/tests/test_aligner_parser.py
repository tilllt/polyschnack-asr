"""Unit-Tests für den Forced-Aligner-Server (Parser + 0-Dauer-Auflösung).

Lauf: python3 -m unittest tests/test_aligner_parser.py -v  (im aligner-service/)
"""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from aligner_server import _parse_alignment, _resolve_zero_duration  # noqa: E402


def _write_json(data) -> str:
    fd, path = tempfile.mkstemp(suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(data, fh)
    return path


class TestParseAlignment(unittest.TestCase):
    def test_json_words_with_confidence(self):
        p = _write_json({"words": [
            {"start": 0.0, "end": 0.32, "word": "Guten", "confidence": 0.98},
            {"start": 0.8, "end": 1.04, "word": "Morgen", "confidence": 0.95},
        ]})
        try:
            words = _parse_alignment(p)
        finally:
            os.unlink(p)
        self.assertEqual(len(words), 2)
        self.assertEqual(words[0]["word"], "Guten")
        self.assertEqual(words[0]["confidence"], 0.98)
        self.assertEqual(words[1]["end"], 1.04)

    def test_json_segments_fallback_key(self):
        p = _write_json({"segments": [{"start": 1.0, "end": 2.0, "text": "Hallo"}]})
        try:
            words = _parse_alignment(p)
        finally:
            os.unlink(p)
        self.assertEqual(len(words), 1)
        self.assertEqual(words[0]["word"], "Hallo")

    def test_plain_lines_format(self):
        fd, p = tempfile.mkstemp(suffix=".txt")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write("0.0 0.5 Hallo Welt\n1.0 1.2 Test\n")
        try:
            words = _parse_alignment(p)
        finally:
            os.unlink(p)
        self.assertEqual(len(words), 2)
        self.assertEqual(words[0]["word"], "Hallo Welt")
        self.assertEqual(words[0]["start"], 0.0)
        self.assertEqual(words[0]["end"], 0.5)

    def test_broken_json_falls_back_to_lines(self):
        p = _write_json({"words": "not-a-list"})
        try:
            words = _parse_alignment(p)
        finally:
            os.unlink(p)
        self.assertEqual(words, [])

    def test_empty_file_returns_empty(self):
        fd, p = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        try:
            words = _parse_alignment(p)
        finally:
            os.unlink(p)
        self.assertEqual(words, [])


class TestResolveZeroDuration(unittest.TestCase):
    def test_zero_duration_gets_next_boundary(self):
        words = [
            {"start": 1.0, "end": 1.0, "word": "a"},
            {"start": 2.0, "end": 2.5, "word": "b"},
        ]
        out = _resolve_zero_duration(words)
        self.assertEqual(out[0]["end"], 2.0)  # nächste Wortgrenze

    def test_zero_duration_last_word_min_duration(self):
        """Change 159: Ein-Wort-Segment mit 0-Dauer kollabiert NICHT mehr
        auf 80 ms — das letzte Wort bekommt mindestens 0,3 s (Karaoke
        überspränge es sonst; vorher end=start+0,08 ohne Start-Rückzug)."""
        words = [{"start": 3.0, "end": 3.0, "word": "last"}]
        out = _resolve_zero_duration(words)
        self.assertAlmostEqual(out[0]["end"], 3.08, places=2)  # end bleibt s+0,08
        self.assertAlmostEqual(out[0]["start"], 2.78, places=2)  # Start rückwärts
        self.assertGreaterEqual(out[0]["end"] - out[0]["start"], 0.29)

    def test_none_start_gets_zero(self):
        words = [{"start": None, "end": None, "word": "x"}]
        out = _resolve_zero_duration(words)
        self.assertEqual(out[0]["start"], 0.0)
        self.assertGreater(out[0]["end"], 0.0)

    def test_confidence_preserved(self):
        words = [{"start": 0.0, "end": 0.2, "word": "x", "confidence": 0.9}]
        out = _resolve_zero_duration(words)
        self.assertEqual(out[0]["confidence"], 0.9)

    def test_normal_words_untouched(self):
        words = [{"start": 0.0, "end": 0.5, "word": "a"}, {"start": 0.5, "end": 1.0, "word": "b"}]
        out = _resolve_zero_duration(words)
        self.assertEqual(out, words)


if __name__ == "__main__":
    unittest.main()
