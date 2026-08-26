"""Tests für den /version-Endpunkt des Aligner-Servers (Change 134).

Lauf: python3 -m unittest tests/test_aligner_version.py -v  (im aligner-service/)

Der Handler ist ein stdlib-BaseHTTPRequestHandler — wir testen die
do_GET-Logik direkt über eine Mini-Instanz (ohne Netzwerk).
"""
import json
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from aligner_server import Handler  # noqa: E402


class _FakeServer:
    pass


def _make_handler(monkey_env=None):
    """Baut einen Handler, dessen _send die Antwort einsammelt statt zu senden."""
    captured = {}

    class _Handler(Handler):
        def _send(self, code, payload):
            captured["code"] = code
            captured["payload"] = payload

    h = _Handler.__new__(_Handler)
    h.path = "/version"
    h._captured = captured  # noqa: SLF001
    return h, captured


class TestVersionEndpoint(unittest.TestCase):
    def test_version_liefert_dev_default(self):
        h, captured = _make_handler()
        with patch.dict(os.environ, {}, clear=False):
            if "GIT_SHA" in os.environ:
                del os.environ["GIT_SHA"]
            h.do_GET()
        self.assertEqual(captured["code"], 200)
        data = captured["payload"]
        self.assertEqual(data["service"], "aligner")
        self.assertEqual(data["commit"], "dev")
        self.assertEqual(data["image_tag"], "dev")

    def test_version_nimmt_git_sha_aus_env(self):
        h, captured = _make_handler()
        with patch.dict(os.environ, {"GIT_SHA": "4a41b46e"}):
            h.do_GET()
        self.assertEqual(captured["code"], 200)
        data = captured["payload"]
        self.assertEqual(data["commit"], "4a41b46e")
        self.assertEqual(data["image_tag"], "4a41b46e")

    def test_version_ist_im_openapi_spec(self):
        # Der Endpunkt soll in der OpenAPI-Spec dokumentiert sein
        repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        spec_path = os.path.join(repo_root, "openapi.json")
        with open(spec_path, encoding="utf-8") as fh:
            spec = json.load(fh)
        self.assertIn("/version", spec["paths"])


if __name__ == "__main__":
    unittest.main()
