"""Tests für die Swagger/OpenAPI-Endpoints des Aligner-Servers.

Lauf: python3 -m unittest tests/test_aligner_docs.py -v  (im aligner-service/)
"""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from aligner_server import _OPENAPI_PATH, _SWAGGER_HTML  # noqa: E402


class TestDocsEndpoints(unittest.TestCase):
    def test_openapi_path_ist_im_container_pfad(self):
        # Der Pfad zeigt ins Container-/app-Verzeichnis (Dockerfile COPY)
        self.assertEqual(_OPENAPI_PATH, "/app/openapi.json")

    def test_swagger_html_ist_gueltiges_html(self):
        self.assertIn("<!DOCTYPE html>", _SWAGGER_HTML)
        self.assertIn("swagger-ui-bundle.js", _SWAGGER_HTML)
        self.assertIn("/openapi.json", _SWAGGER_HTML)

    def test_swagger_html_hat_keine_credentials_im_url(self):
        # Swagger-UI lädt die Spec relativ — kein Hardcode auf externen Host
        self.assertNotIn("http://", _SWAGGER_HTML.split("unpkg.com")[0])


class TestSpecFile(unittest.TestCase):
    def test_openapi_json_ist_gueltig_und_vollstaendig(self):
        repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        spec_path = os.path.join(repo_root, "openapi.json")
        self.assertTrue(os.path.isfile(spec_path), "openapi.json fehlt im Repo")
        with open(spec_path, encoding="utf-8") as fh:
            spec = json.load(fh)
        self.assertEqual(spec["openapi"].split(".")[0], "3")
        paths = spec["paths"]
        self.assertIn("/v1/audio/align", paths)
        self.assertIn("/health", paths)
        # Das align-POST braucht multipart mit file + text
        props = paths["/v1/audio/align"]["post"]["requestBody"]["content"][
            "multipart/form-data"]["schema"]["properties"]
        self.assertIn("file", props)
        self.assertIn("text", props)
        self.assertIn("lang", props)
