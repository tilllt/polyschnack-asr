"""Client für den Forced-Aligner-Service (crispr-align, Port 5099).

Der Aligner verifiziert jede Wortgrenze gegen die echte Akustik
(qwen3-forced-aligner, einzelner nicht-autoregressiver Forward-Pass) —
ersetzt die groben Modell-Word-Timestamps, die bei langen Audios über
Chunk-Grenzen driften (Karaoke-Sync).

Konfiguration:
  CRISP_ALIGN_URL          Default http://crispr-align:5099
  POLYSCHNACK_ALIGN_WORDS  "false" deaktiviert die Phase komplett
                           (Default: aktiv, wenn der Service erreichbar ist)
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

import httpx

log = logging.getLogger(__name__)

ALIGN_URL = os.getenv("CRISP_ALIGN_URL", "http://crispr-align:5099").rstrip("/")
ALIGN_WORDS_ENABLED = os.getenv("POLYSCHNACK_ALIGN_WORDS", "true").lower() not in (
    "0", "false", "off", "no", ""
)


class AlignerClient:
    """HTTP-Client für POST /v1/audio/align (multipart file+text+lang)."""

    def __init__(self, url: Optional[str] = None, timeout: float = 900.0):
        self.url = (url or ALIGN_URL).rstrip("/")
        self._timeout = httpx.Timeout(connect=5.0, read=timeout, write=timeout, pool=5.0)

    def health(self) -> bool:
        """Schneller Erreichbarkeits-Check (2 s) — für das Skip-if-down der Phase."""
        try:
            r = httpx.get(f"{self.url}/health", timeout=2.0)
            return r.status_code == 200
        except Exception:
            return False

    def status(self) -> dict:
        """Live-Status des Aligner-Prozesses (Herzschlag).

        Liefert z.B. ``{active, started_at, last_beat_at, last_line,
        progress_pct, elapsed_s, last_beat_ago_s}`` — oder ``{}`` wenn der
        Container /status nicht kennt (ältere Version).
        """
        try:
            r = httpx.get(f"{self.url}/status", timeout=3.0)
            if r.status_code == 200:
                return r.json()
        except Exception:
            pass
        return {}

    def align(self, audio_bytes: bytes, text: str, lang: str = "de") -> List[Dict[str, Any]]:
        """Aligne Audio + Referenztext → [{start, end, word}, ...] (Sekunden, relativ)."""
        try:
            r = httpx.post(
                f"{self.url}/v1/audio/align",
                files={"file": ("audio.wav", audio_bytes, "audio/wav")},
                data={"text": text, "lang": lang},
                timeout=self._timeout,
            )
        except Exception as exc:
            raise RuntimeError(f"Aligner nicht erreichbar ({type(exc).__name__})") from exc
        if r.status_code != 200:
            detail = ""
            try:
                detail = (r.json().get("error") or "")[:300]
            except Exception:
                detail = r.text[:200]
            raise RuntimeError(f"Aligner-Fehler {r.status_code}: {detail or 'unbekannt'}")
        return r.json().get("words", [])
