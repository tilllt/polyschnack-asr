"""LLM-Chat über einen OpenAI-kompatiblen Endpunkt (Task D1).

Konfiguration per Env (POLYSCHNACK_LLM_URL/API_KEY/MODEL). Basis für
Prompt-Templates (D2) und den A13-Enhance-Pass.
"""
from __future__ import annotations

from typing import Optional

import httpx

from .config import settings


def chat(system: str, user_text: str, max_tokens: int = 2000,
         endpoint: Optional[dict] = None) -> str:
    """Chat über einen OpenAI-kompatiblen Endpunkt.

    ``endpoint`` = BYOK-Override (Task E3): {"base_url", "api_key", "model"} —
    gewinnt vor den Server-Env-Einstellungen. Ohne beides: RuntimeError.
    """
    url = (endpoint or {}).get("base_url") or settings.POLYSCHNACK_LLM_URL
    key = (endpoint or {}).get("api_key") or settings.POLYSCHNACK_LLM_API_KEY
    model = (endpoint or {}).get("model") or settings.POLYSCHNACK_LLM_MODEL
    if not url or not key:
        raise RuntimeError("LLM-Endpunkt nicht konfiguriert (Server-Env oder BYOK nötig)")
    r = httpx.post(
        f"{url.rstrip('/')}/chat/completions",
        headers={"Authorization": f"Bearer {key}"},
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user_text},
            ],
            "max_tokens": max_tokens,
        },
        timeout=120,
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]
