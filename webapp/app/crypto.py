"""Fernet-Verschlüsselung für Delivery-Credentials (Task D3).

Key wird deterministisch aus SESSION_SECRET abgeleitet — kein zusätzlicher
Secret-Management-Aufwand, aber die DB-Werte sind ohne das Secret wertlos.
Review 2026-08-15 (P1.4): der frühere sha256("dev")-Fallback ist entfernt —
SESSION_SECRET kommt jetzt aus config.py (Env oder persistierte Datei) und
ist nie leer. Ein leerer Key hier = Konfigurationsfehler, kein stiller
Fallback.
"""
from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet

from .config import settings

_secret = (settings.SESSION_SECRET or "").strip()
if not _secret:
    raise RuntimeError(
        "SESSION_SECRET ist leer — Verschlüsselung der Delivery-Credentials "
        "würde mit einem bekannten Schlüssel signieren. Env-Var setzen oder "
        "DATA_DIR beschreibbar machen (persistierte Erzeugung)."
    )

_KEY = Fernet(base64.urlsafe_b64encode(
    hashlib.sha256(_secret.encode()).digest()
))


def encrypt(plain: str) -> str:
    return _KEY.encrypt(plain.encode()).decode()


def decrypt(cipher: str) -> str:
    return _KEY.decrypt(cipher.encode()).decode()
