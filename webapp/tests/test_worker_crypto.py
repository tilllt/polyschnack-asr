"""Tests für worker/crypto.py — AES-256-GCM Job-Transfer (Change 020).

Rundtrips (Bytes + Datei, inkl. Multi-Chunk), Manipulationsabwehr und
Schlüssel-Validierung. Bewusst ohne echte Geheimnisse — Schlüssel werden
im Test erzeugt.
"""
import os

import pytest

from app.worker.crypto import (
    CryptoError,
    cleanup_tmpfs,
    decrypt_bytes,
    decrypt_file,
    encrypt_bytes,
    encrypt_file,
    generate_key,
    key_from_env,
    key_to_env,
    tmpfs_dir,
)

# Sicherstellen, dass ein Chunk-Wechsel getestet wird:
TINY_CHUNK = 64
BIG_PAYLOAD = os.urandom(200_000)  # > 3 × TINY_CHUNK


def test_key_roundtrip():
    key = generate_key()
    env = key_to_env(key)
    assert len(env) > 40
    assert key_from_env(env) == key


def test_key_rejects_wrong_length():
    with pytest.raises(CryptoError):
        key_from_env("aGVsbG8=")  # 5 Bytes statt 32


def test_bytes_roundtrip():
    key = generate_key()
    blob = encrypt_bytes(BIG_PAYLOAD, key)
    assert decrypt_bytes(blob, key) == BIG_PAYLOAD


def test_bytes_wrong_key_fails():
    key = generate_key()
    other = generate_key()
    blob = encrypt_bytes(b"geheim", key)
    with pytest.raises(CryptoError):
        decrypt_bytes(blob, other)


def test_bytes_tamper_fails():
    key = generate_key()
    blob = bytearray(encrypt_bytes(b"geheim", key))
    blob[-1] ^= 0xFF  # Tag/Nutzdaten verändern
    with pytest.raises(CryptoError):
        decrypt_bytes(bytes(blob), key)


def test_file_roundtrip_multichunk(tmp_path):
    key = generate_key()
    src = tmp_path / "audio.wav"
    enc = tmp_path / "audio.wav.enc"
    dec = tmp_path / "audio.wav.dec"
    src.write_bytes(BIG_PAYLOAD)
    encrypt_file(src, enc, key, chunk_size=TINY_CHUNK)
    decrypt_file(enc, dec, key)
    assert dec.read_bytes() == BIG_PAYLOAD
    # Chiffre ist größer (nonce+tag je Chunk) und kein Klartext:
    assert enc.stat().st_size > src.stat().st_size
    assert b"PSW1" == enc.read_bytes()[:4]


def test_file_wrong_key_fails(tmp_path):
    key = generate_key()
    src = tmp_path / "a.wav"
    enc = tmp_path / "a.wav.enc"
    src.write_bytes(b"vertraulich")
    encrypt_file(src, enc, key, chunk_size=TINY_CHUNK)
    with pytest.raises(CryptoError):
        decrypt_file(enc, tmp_path / "out.bin", generate_key())


def test_file_truncated_fails(tmp_path):
    key = generate_key()
    src = tmp_path / "a.wav"
    enc = tmp_path / "a.wav.enc"
    src.write_bytes(BIG_PAYLOAD)
    encrypt_file(src, enc, key, chunk_size=TINY_CHUNK)
    cut = enc.read_bytes()[:-20]  # Ende abschneiden
    enc.write_bytes(cut)
    with pytest.raises(CryptoError):
        decrypt_file(enc, tmp_path / "out.bin", key)


def test_file_not_psw1_fails(tmp_path):
    bogus = tmp_path / "bogus.enc"
    bogus.write_bytes(b"nicht verschluesselt")
    with pytest.raises(CryptoError):
        decrypt_file(bogus, tmp_path / "out.bin", generate_key())


def test_tmpfs_dir_cleanup(tmp_path):
    d = tmpfs_dir("job-42", base=str(tmp_path))
    assert d.is_dir()
    probe = d / "audio.dec"
    probe.write_bytes(b"klartext")
    cleanup_tmpfs(d)
    assert not d.exists()
