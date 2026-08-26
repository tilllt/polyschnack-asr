"""Tests für den /version-Endpunkt des SEP-Servers (Change 134).

Lauf: python3 -m unittest tests/test_sep_version.py -v  (im sep-service/)
"""
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sep_server import Handler  # noqa: E402


def _make_handler():
    captured = {}

    class _Handler(Handler):
        def _send(self, code, payload, ctype="application/json"):
            captured["code"] = code
            captured["payload"] = payload

    h = _Handler.__new__(_Handler)
    h.path = "/version"
    return h, captured


class TestVersionEndpoint(unittest.TestCase):
    def test_version_liefert_dev_default(self):
        h, captured = _make_handler()
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("GIT_SHA", None)
            h.do_GET()
        self.assertEqual(captured["code"], 200)
        data = captured["payload"]
        self.assertEqual(data["service"], "separator")
        self.assertEqual(data["commit"], "dev")

    def test_version_nimmt_git_sha_aus_env(self):
        h, captured = _make_handler()
        with patch.dict(os.environ, {"GIT_SHA": "4a41b46e"}):
            h.do_GET()
        self.assertEqual(captured["code"], 200)
        self.assertEqual(captured["payload"]["commit"], "4a41b46e")


if __name__ == "__main__":
    unittest.main()
