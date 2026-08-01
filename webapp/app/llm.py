"""LLM-Chat über einen OpenAI-kompatiblen Endpunkt (Task D1).

Konfiguration per Env (POLYSCHNACK_LLM_URL/API_KEY/MODEL). Basis für
Prompt-Templates (D2) und den A13-Enhance-Pass.
"""
from __future__ import annotations

import httpx

from .config import settings


def chat(system: str, user_text: str, max_tokens: int = 2000) -> str:
    if not settings.POLYSCHNACK_LLM_API_KEY:
        raise RuntimeError("POLYSCHNACK_LLM_API_KEY nicht konfiguriert")
    if not settings.POLYSCHNACK_LLM_URL:
        raise RuntimeError("POLYSCHNACK_LLM_URL nicht konfiguriert")
    r = httpx.post(
        f"{settings.POLYSCHNACK_LLM_URL.rstrip('/')}/chat/completions",
        headers={"Authorization": f"Bearer {settings.POLYSCHNACK_LLM_API_KEY}"},
        json={
            "model": settings.POLYSCHNACK_LLM_MODEL,
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
