"""OpenAPI-Spezifikationen für ALLE PolySchnack-Container (2026-08-15).

Zweck: Jeder Backend-Container (ONNX, pk-cpp, qwen3, moonshine-de, ark,
canary, diar, aligner) soll einzeln benutzbar und dokumentiert sein. Die
Webapp aggregiert die Specs unter /api-docs (Swagger-UI) und serviert sie
unter /api/specs/<name>.json. Der Aligner-Service liefert sein
/openapi.json zusätzlich selbst aus.

Die C++-Backends (CrispASR/qwen3-asr-server) exposieren alle dieselbe
OpenAI-kompatible Transkriptions-API (docs/API.md): POST
/v1/audio/transcriptions mit response_format json/text/verbose_json/srt/vtt
+ timestamp_granularities=word. Deshalb eine gemeinsame Basis-Spec, die pro
Container nur Name/Beschreibung/Server-URL variiert.
"""
from __future__ import annotations

import json
from typing import Any, Dict

#: Gemeinsame OpenAI-kompatible Transkriptions-Spec (Basis für ASR-Container).
def _transcription_spec(title: str, description: str, server_url: str,
                        model_enum: list[str] | None = None,
                        extra_paths: dict[str, Any] | None = None) -> dict[str, Any]:
    paths: dict[str, Any] = {
        "/v1/audio/transcriptions": {
            "post": {
                "summary": "Transcribe Audio (OpenAI-kompatibel)",
                "description": (
                    "OpenAI-kompatible Audio-Transkription. Nutzbar mit dem "
                    "OpenAI SDK / jedem OpenAI-Tool per base_url-Override.\n\n"
                    "Formate: alles was ffmpeg dekodiert (mp3, wav, ogg/opus, "
                    "m4a, flac, webm, …)."
                ),
                "operationId": "create_transcription",
                "requestBody": {
                    "required": True,
                    "content": {
                        "multipart/form-data": {
                            "schema": {
                                "type": "object",
                                "required": ["file"],
                                "properties": {
                                    "file": {
                                        "type": "string",
                                        "format": "binary",
                                        "description": "Audiodatei (nicht Dateiname).",
                                    },
                                    "model": {
                                        "type": "string",
                                        "default": model_enum[0] if model_enum else "parakeet-tdt-0.6b-v3",
                                        "enum": model_enum or None,
                                        "description": "Modell-/Backend-Variante.",
                                    },
                                    "language": {
                                        "type": "string",
                                        "description": "Sprachcode (z.B. 'de', 'en', 'pt') — optional.",
                                    },
                                    "response_format": {
                                        "type": "string",
                                        "default": "json",
                                        "enum": ["json", "text", "verbose_json", "srt", "vtt"],
                                        "description": "Ausgabeformat. verbose_json liefert segments[] mit start/end/text.",
                                    },
                                    "timestamp_granularities": {
                                        "type": "array",
                                        "items": {"type": "string"},
                                        "description": "['word'] für Wort-Zeitstempel (mit verbose_json).",
                                    },
                                },
                            }
                        }
                    },
                },
                "responses": {
                    "200": {
                        "description": "Transkriptionsergebnis",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "oneOf": [
                                        {"type": "object", "properties": {"text": {"type": "string"}}},
                                        {"type": "object",
                                         "properties": {
                                             "text": {"type": "string"},
                                             "duration": {"type": "number"},
                                             "segments": {
                                                 "type": "array",
                                                 "items": {
                                                     "type": "object",
                                                     "properties": {
                                                         "id": {"type": "integer"},
                                                         "start": {"type": "number"},
                                                         "end": {"type": "number"},
                                                         "text": {"type": "string"},
                                                     },
                                                 },
                                             },
                                         }},
                                    ]
                                }
                            },
                            "text/plain": {"schema": {"type": "string"}},
                        },
                    },
                    "422": {"description": "Datei fehlt / nicht dekodierbar"},
                },
            }
        },
        "/health": {
            "get": {
                "summary": "Liveness + Selbstauskunft",
                "operationId": "health",
                "responses": {
                    "200": {
                        "description": "Status, Modell, Device",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "status": {"type": "string"},
                                        "model": {"type": "string"},
                                        "device": {"type": "string"},
                                    },
                                }
                            }
                        },
                    }
                },
            }
        },
    }
    if extra_paths:
        paths.update(extra_paths)
    return {
        "openapi": "3.0.0",
        "info": {"title": title, "description": description, "version": "1.0.0"},
        "servers": [{"url": server_url}],
        "paths": paths,
    }


#: Aligner-Spec (eigene API — kein OpenAI-Standard).
ALIGNER_SPEC: dict[str, Any] = {
    "openapi": "3.0.0",
    "info": {
        "title": "PolySchnack Forced-Aligner",
        "description": (
            "Wort-Zeitstempel (Karaoke-Sync): aligniert den Referenztext gegen "
            "die Akustik (qwen3-forced-aligner). EIN Request gleichzeitig "
            "(ggml-Modell resident); max. 400 s Audio pro Request — längere "
            "Audios in Chunks schneiden und je Chunk den passenden Text senden."
        ),
        "version": "1.0.0",
    },
    "servers": [{"url": "http://crispr-align:5099"}],
    "paths": {
        "/v1/audio/align": {
            "post": {
                "summary": "Forced Alignment",
                "description": "Liefert Wort-für-Wort-Zeitstempel zum Referenztext.",
                "operationId": "align",
                "requestBody": {
                    "required": True,
                    "content": {
                        "multipart/form-data": {
                            "schema": {
                                "type": "object",
                                "required": ["file", "text"],
                                "properties": {
                                    "file": {
                                        "type": "string",
                                        "format": "binary",
                                        "description": "Audiodatei (max 400 s, max 512 MB).",
                                    },
                                    "text": {
                                        "type": "string",
                                        "description": "Referenztext zum Alignieren.",
                                    },
                                    "lang": {
                                        "type": "string",
                                        "default": "de",
                                        "enum": ["de", "en"],
                                    },
                                },
                            }
                        }
                    },
                },
                "responses": {
                    "200": {
                        "description": "Wort-Timestamps",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "words": {
                                            "type": "array",
                                            "items": {
                                                "type": "object",
                                                "properties": {
                                                    "word": {"type": "string"},
                                                    "start": {"type": "number"},
                                                    "end": {"type": "number"},
                                                    "confidence": {"type": "number", "nullable": True},
                                                },
                                            },
                                        },
                                        "language": {"type": "string"},
                                        "duration_s": {"type": "number"},
                                    },
                                }
                            }
                        },
                    },
                    "422": {"description": "file/text fehlt oder Audio > 400 s"},
                    "413": {"description": "Upload zu groß (> 512 MB)"},
                },
            }
        },
        "/health": {
            "get": {
                "summary": "Liveness + Features",
                "operationId": "health",
                "responses": {
                    "200": {
                        "description": "Status, Modell, max_duration_s, confidence (ehrlich: false)",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "status": {"type": "string"},
                                        "service": {"type": "string"},
                                        "model": {"type": "string"},
                                        "max_duration_s": {"type": "number"},
                                        "word_timestamps": {"type": "boolean"},
                                        "confidence": {"type": "boolean"},
                                        "languages": {"type": "array", "items": {"type": "string"}},
                                        "device": {"type": "string"},
                                    },
                                }
                            }
                        },
                    }
                },
            }
        },
    },
}


def build_specs() -> dict[str, dict[str, Any]]:
    """Alle Container-Specs — Key = Name im /api/specs/<name>.json-Pfad."""
    asr_base = (
        "OpenAI-kompatible Audio-Transkription. Nutzbar mit dem OpenAI SDK "
        "(base_url=<host>/v1, api_key beliebig), curl oder jedem OpenAI-Client."
    )
    return {
        "ps-pk-onnx": _transcription_spec(
            "PolySchnack ASR (ONNX Parakeet)",
            asr_base + " ONNX-optimiert (Parakeet TDT 0.6b v3).",
            "http://localhost:5092",
            ["parakeet-tdt-0.6b-v3", "istupakov/parakeet-tdt-0.6b-v3-onnx",
             "grikdotnet/parakeet-tdt-0.6b-fp16"],
        ),
        "crispr-pk-cpp": _transcription_spec(
            "PolySchnack ASR (Parakeet.cpp)",
            asr_base + " C++-Backend (ggml, GPU).",
            "http://localhost:5093",
            ["parakeet-tdt-0.6b-v3"],
        ),
        "crispr-qwen3": _transcription_spec(
            "PolySchnack ASR (Qwen3)",
            asr_base + " Qwen3-ASR 0.6B (ggml, GPU).",
            "http://localhost:5094",
            ["qwen3-asr-0.6b"],
        ),
        "crispr-moonshine-de": _transcription_spec(
            "PolySchnack ASR (Moonshine DE)",
            asr_base + " Moonshine Deutsch (ggml, GPU).",
            "http://localhost:5095",
            ["moonshine-de"],
        ),
        "crispr-ark": _transcription_spec(
            "PolySchnack ASR (ARK)",
            asr_base + " ARK-Transkription (ggml, GPU).",
            "http://localhost:5096",
            ["ark"],
        ),
        "crispr-canary": _transcription_spec(
            "PolySchnack ASR (Canary)",
            asr_base + " Canary-Transkription (ggml, GPU).",
            "http://localhost:5097",
            ["canary"],
        ),
        "crispr-diar": _transcription_spec(
            "PolySchnack Diarization",
            asr_base + " Sprecher-Diarisierung (Parakeet + diar).",
            "http://localhost:5098",
            ["parakeet-tdt-0.6b-v3"],
            extra_paths={
                "/v1/audio/diarize": {
                    "post": {
                        "summary": "Sprecher-Diarisierung",
                        "operationId": "diarize",
                        "requestBody": {
                            "required": True,
                            "content": {
                                "multipart/form-data": {
                                    "schema": {
                                        "type": "object",
                                        "required": ["file"],
                                        "properties": {
                                            "file": {"type": "string", "format": "binary"},
                                            "num_speakers": {"type": "integer", "description": "Optional: bekannte Sprecherzahl."},
                                        },
                                    }
                                }
                            },
                        },
                        "responses": {"200": {"description": "Segmente mit Sprecher-Labels"}},
                    }
                }
            },
        ),
        "crispr-align": ALIGNER_SPEC,
        # OpenAI-kompatibler Proxy der Webapp (Backend-Hopping via model).
        "ps-webapp-openai": _transcription_spec(
            "PolySchnack OpenAI-Proxy (Webapp)",
            (
                "OpenAI-kompatibler Transkriptions-Endpoint der Webapp — "
                "Backend-Hopping über den model-Parameter (ps-pk-onnx, "
                "crispr-qwen3, …). Auth: API-Key aus den Settings "
                "(Authorization: Bearer <key>). Nutzbar mit dem OpenAI SDK: "
                "OpenAI(base_url='https://<host>/v1', api_key='<key>')."
            ),
            "https://<host>/v1",
            ["parakeet-tdt-0.6b-v3", "qwen3-asr-0.6b", "moonshine-de",
             "ark", "canary", "parakeet-cpp"],
        ),
    }


def spec_json(name: str) -> str:
    """JSON-String der Spec (für den /api/specs-Endpoint)."""
    return json.dumps(build_specs()[name], ensure_ascii=False, indent=2)
