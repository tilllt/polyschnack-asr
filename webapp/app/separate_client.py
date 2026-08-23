"""Client für den Source-Separation-Service (crispr-sep, Port 5100).

Change 106: Music-Removal als Pre-Processing für ASR + Aligner. Die
Webapp schickt Audio + Backend-Wahl (htdemucs | mel-band-roformer) und
bekommt den vocals-Stem als 44.1-kHz-Stereo-WAV zurück — Gesang isoliert,
Musik entfernt. Karaoke-/Gesangsaufnahmen (z. B. saisoncouplet) lassen
sich damit für ASR und Forced-Aligner besser verorten.

Ehrlicher Fehlerpfad: Der Aufrufer (service.py) läuft bei down/leer/
Fehler mit dem Original-Audio weiter — diese Phase darf eine Transkription
nie blockieren oder still verschlucken.

Konfiguration:
  CRISP_SEP_URL          Default http://crispr-sep:5100
  POLYSCHNACK_SEPARATE   "false" deaktiviert die Phase komplett
                         (Default: aktiv, wenn der Service erreichbar ist)
"""
from __future__ import annotations

import logging
import os
from typing import Optional

import httpx

log = logging.getLogger(__name__)

SEP_URL = os.getenv("CRISP_SEP_URL", "http://crispr-sep:5100").rstrip("/")
SEP_ENABLED = os.getenv("POLYSCHNACK_SEPARATE", "true").lower() not in (
    "0", "false", "off", "no", ""
)
SEP_BACKENDS = ("htdemucs", "mel-band-roformer")


class SeparateClient:
    """HTTP-Client für POST /v1/audio/separate (multipart file+backend)."""

    def __init__(self, url: Optional[str] = None, timeout: float = 3600.0):
        self.url = (url or SEP_URL).rstrip("/")
        self._timeout = httpx.Timeout(connect=5.0, read=timeout, write=timeout, pool=5.0)

    def health(self) -> bool:
        """Schneller Erreichbarkeits-Check (2 s) — für das Skip-if-down."""
        try:
            r = httpx.get(f"{self.url}/health", timeout=2.0)
            return r.status_code == 200
        except Exception:
            return False

    def status(self) -> dict:
        """Live-Status des Separations-Prozesses (Herzschlag)."""
        try:
            r = httpx.get(f"{self.url}/status", timeout=3.0)
            if r.status_code == 200:
                return r.json()
        except Exception:
            pass
        return {}

    def separate(self, audio_bytes: bytes, backend: str = "htdemucs") -> Optional[bytes]:
        """Separiere Audio → vocals.wav (bytes) | None (kein Ergebnis).

        *backend*: "htdemucs" | "mel-band-roformer" (siehe SEP_BACKENDS).
        None bei: Service down, HTTP-Fehler, leerer vocals-Ausgabe — der
        Aufrufer fällt dann auf das Original-Audio zurück.
        """
        if backend not in SEP_BACKENDS:
            log.warning("separate: unbekanntes Backend %r — übersprungen", backend)
            return None
        try:
            r = httpx.post(
                f"{self.url}/v1/audio/separate",
                files={"file": ("audio.wav", audio_bytes, "audio/wav")},
                data={"backend": backend},
                timeout=self._timeout,
            )
        except Exception as exc:
            log.warning("separate: Service nicht erreichbar (%s)", type(exc).__name__)
            return None
        if r.status_code != 200:
            detail = ""
            try:
                detail = (r.json().get("error") or "")[:200]
            except Exception:
                detail = r.text[:150]
            log.warning("separate: Fehler %s: %s", r.status_code, detail or "unbekannt")
            return None
        if not r.content:
            log.warning("separate: leere Antwort (keine vocals)")
            return None
        return r.content
