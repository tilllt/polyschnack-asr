"""worker/crypto.py — AES-256-GCM für den Job-Transfer (Change 020).

Audio verlässt die Box NUR als Chiffre; der Worker entschlüsselt
ausschließlich in tmpfs (RAM), Klartext berührt nie die Instance-Disk.

Schlüssel-Handling:
- Einmal-Schlüssel pro Job (256 Bit), generiert auf der Box.
- Transport als base64-String in der Instance-Env (nie im Image).
- Nach Jobende wertlos; Rotation pro Job.

Dateiformat (chunked GCM, streamingfähig für große Audio-Dateien):
    Header:  Magic b"PSW1" (4 B) + chunk_size (4 B, big-endian)
    Je Chunk: nonce (12 B) + AES-256-GCM-Ciphertext (chunk + 16 B Tag)
    AAD je Chunk = Chunk-Index (4 B, big-endian) → Reorder-Schutz.
"""
from __future__ import annotations

import base64
import secrets
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

KEY_BYTES = 32          # AES-256
NONCE_BYTES = 12        # GCM-Standard-Nonce
MAGIC = b"PSW1"
DEFAULT_CHUNK = 4 * 1024 * 1024   # 4 MiB
DEFAULT_TMPFS = "/dev/shm"


class CryptoError(ValueError):
    """Entschlüsselungsfehler (falscher Schlüssel, Manipulation, Format)."""


# ── Schlüssel ────────────────────────────────────────────────────────────

def generate_key() -> bytes:
    """Frischer Einmal-Schlüssel (256 Bit) für einen Job."""
    return secrets.token_bytes(KEY_BYTES)


def key_to_env(key: bytes) -> str:
    """Schlüssel als base64-String für die Instance-Env."""
    return base64.urlsafe_b64encode(key).decode("ascii")


def key_from_env(env: str | bytes) -> bytes:
    """base64-Env-String → Schlüssel; validiert die Länge."""
    raw = env.encode("ascii") if isinstance(env, str) else env
    key = base64.urlsafe_b64decode(raw)
    if len(key) != KEY_BYTES:
        raise CryptoError(f"Schlüssel muss {KEY_BYTES} Bytes haben, hat {len(key)}")
    return key


# ── Bytes (kleine Payloads: JSON-Ergebnisse, Hypothese) ──────────────────

def encrypt_bytes(plain: bytes, key: bytes) -> bytes:
    """nonce + ciphertext+tag als ein Blob."""
    nonce = secrets.token_bytes(NONCE_BYTES)
    return nonce + AESGCM(key).encrypt(nonce, plain, None)


def decrypt_bytes(blob: bytes, key: bytes) -> bytes:
    """Gegenstück zu encrypt_bytes; wirft CryptoError bei Manipulation."""
    if len(blob) < NONCE_BYTES + 16:
        raise CryptoError("Blob zu kurz für nonce+ciphertext+tag")
    nonce, ct = blob[:NONCE_BYTES], blob[NONCE_BYTES:]
    try:
        return AESGCM(key).decrypt(nonce, ct, None)
    except Exception as e:  # cryptography: InvalidTag u. a.
        raise CryptoError(f"Entschlüsselung fehlgeschlagen: {e}") from e


# ── Dateien (Streaming, chunked GCM) ─────────────────────────────────────

def encrypt_file(src: Path, dst: Path, key: bytes, chunk_size: int = DEFAULT_CHUNK) -> None:
    """Verschlüsselt src streaming nach dst (Header + Chunks)."""
    aes = AESGCM(key)
    with open(src, "rb") as fin, open(dst, "wb") as fout:
        fout.write(MAGIC)
        fout.write(chunk_size.to_bytes(4, "big"))
        idx = 0
        while True:
            chunk = fin.read(chunk_size)
            if not chunk:
                break
            nonce = secrets.token_bytes(NONCE_BYTES)
            aad = idx.to_bytes(4, "big")
            fout.write(nonce + aes.encrypt(nonce, chunk, aad))
            idx += 1


def decrypt_file(src: Path, dst: Path, key: bytes) -> None:
    """Entschlüsselt streaming nach dst (tmpfs!). Wirft CryptoError bei
    Manipulation (falscher Schlüssel, getauschte Chunks, abgeschnittene Datei)."""
    aes = AESGCM(key)
    with open(src, "rb") as fin, open(dst, "wb") as fout:
        header = fin.read(8)
        if header[:4] != MAGIC:
            raise CryptoError("Kein PSW1-Format (Magic fehlt)")
        chunk_size = int.from_bytes(header[4:8], "big")
        if chunk_size <= 0 or chunk_size > 64 * 1024 * 1024:
            raise CryptoError(f"Ungültige chunk_size: {chunk_size}")
        idx = 0
        while True:
            nonce = fin.read(NONCE_BYTES)
            if not nonce:
                break  # sauberes Ende
            ct = fin.read(chunk_size + 16)
            if len(ct) != chunk_size + 16:
                raise CryptoError("Datei abgeschnitten (letzter Chunk unvollständig)")
            aad = idx.to_bytes(4, "big")
            try:
                plain = aes.decrypt(nonce, ct, aad)
            except Exception as e:
                raise CryptoError(f"Entschlüsselung fehlgeschlagen (Chunk {idx}): {e}") from e
            fout.write(plain)
            idx += 1


# ── tmpfs-Helfer (Klartext nur im RAM) ───────────────────────────────────

def tmpfs_dir(job_id: str, base: str = DEFAULT_TMPFS) -> Path:
    """Job-Verzeichnis im tmpfs (RAM) anlegen — Klartext nie auf Disk.

    base ist im Test überschreibbar; im Betrieb /dev/shm.
    """
    d = Path(base) / f"psworker-{job_id}"
    d.mkdir(mode=0o700, parents=True, exist_ok=True)
    return d


def cleanup_tmpfs(directory: Path) -> None:
    """Job-Verzeichnis vollständig entfernen (Aufräumen nach dem Job)."""
    if directory.exists():
        for f in directory.iterdir():
            f.unlink(missing_ok=True)
        directory.rmdir()
