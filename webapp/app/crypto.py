"""Fernet-Verschlüsselung für Delivery-Credentials (Task D3).

Key wird deterministisch aus SESSION_SECRET abgeleitet — kein zusätzlicher
Secret-Management-Aufwand, aber die DB-Werte sind ohne das Secret wertlos.
"""
from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet

from .config import settings

_KEY = Fernet(base64.urlsafe_b64encode(
    hashlib.sha256((settings.SESSION_SECRET or "dev").encode()).digest()
))


def encrypt(plain: str) -> str:
    return _KEY.encrypt(plain.encode()).decode()


def decrypt(cipher: str) -> str:
    return _KEY.decrypt(cipher.encode()).decode()
