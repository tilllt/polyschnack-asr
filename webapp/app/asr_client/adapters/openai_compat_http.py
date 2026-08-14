"""OpenAI-kompatibler Remote-ASR-Adapter (Whisper-API, Mistral Voxtral, Groq, ...).

Nutzt ``POST {base_url}/audio/transcriptions`` im OpenAI-Format
(verbose_json + word-Timestamps) mit optionaler Bearer-Auth — damit
funktionieren alle Anbieter, die die OpenAI-Whisper-API nachbauen.

Konfiguration NUR ueber backends.yaml-Eintraege (``type: remote``,
auskommentierte Beispiele unten) + Env-Variablen — API-Keys gehoeren nie
ins YAML/Repo, sondern in die Container-Env (z. B. OPENAI_API_KEY):

    adapter: app.asr_client.adapters.openai_compat_http:OpenAiCompatHttpClient
    adapter_kwargs:
      base_url: https://api.openai.com/v1   # inkl. API-Prefix (/v1)
      api_key_env: OPENAI_API_KEY           # Env-Var-Name mit dem Key
      model: whisper-1

Bekannte base_urls (Stand 2026-08):
    OpenAI  https://api.openai.com/v1                  (model: whisper-1)
    Mistral https://api.mistral.ai/v1                  (model: voxtral)
    Groq    https://api.groq.com/openai/v1             (model: whisper-large-v3)

URL-Aufloesung: ``base_url`` (adapter_kwargs) gewinnt ueber die sonst
automatische Compose-/Env-URL (Option C) — ein Remote-Backend hat keinen
Container im Compose-Netz. Alternativ die Env-Variable ``<ID>_URL`` setzen.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import httpx

from .. import AsrClient, BackendCapabilities, _parse_result

log = logging.getLogger(__name__)


class OpenAiCompatHttpClient(AsrClient):
    """Transkribiert ueber eine OpenAI-kompatible /audio/transcriptions-API."""

    capabilities = BackendCapabilities(
        streaming=False,
        async_jobs=False,
        noise_reduce=False,
        word_timestamps=True,  # verbose_json + timestamp_granularities=word
        languages=["de", "en"],
        device=["remote"],
        label="openai-compat",
        native_punctuation=True,  # Whisper-Familie liefert Interpunktion nativ
        accepts_compressed=True,  # Anbieter dekodieren MP3/OGG selbst
    )

    def __init__(
        self,
        url: Optional[str] = None,
        base_url: Optional[str] = None,
        api_key: str = "",
        model: str = "whisper-1",
        transport: Optional[httpx.BaseTransport] = None,
        capabilities: Optional[BackendCapabilities] = None,
    ) -> None:
        # base_url (adapter_kwargs) gewinnt ueber die automatische
        # Compose-/Env-URL (Option C) — remote hat keinen Container.
        self.url = (base_url or url or "https://api.openai.com/v1").rstrip("/")
        self.api_key = api_key
        self.model = model
        self._transport = transport
        if capabilities is not None:
            self.capabilities = capabilities

    def transcribe(
        self, audio_bytes: bytes, filename: str, mime: str,
        noise_reduce: bool = True,
    ) -> Dict[str, Any]:
        """Transcribe via POST {base_url}/audio/transcriptions (verbose_json)."""
        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        data = {
            "model": self.model,
            "response_format": "verbose_json",
            "timestamp_granularities": "word",
        }
        try:
            with httpx.Client(timeout=3600, transport=self._transport) as client:
                resp = client.post(
                    f"{self.url}/audio/transcriptions",
                    headers=headers,
                    files={"file": (filename, audio_bytes, mime)},
                    data=data,
                )
                resp.raise_for_status()
                return _parse_result(resp.json())
        except httpx.ConnectError as exc:
            raise RuntimeError(
                f"Remote-Backend {self.url} nicht erreichbar. "
                "base_url/adapter_kwargs und API-Key-Env pruefen."
            ) from exc
