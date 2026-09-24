"""
AetherControl - Cryptography Utilities

Key exchange, session token generation, and device identity management.

Security model:
- Each server has a persistent ECDSA identity key pair (P-256)
- Pairing: ECDH key exchange → derive shared secret → HKDF → session key
- Session tokens: random 32-byte tokens, HMAC-validated per request
- All wire communication uses TLS 1.3 (handled by asyncio ssl context)

IMPORTANT: Private keys and session tokens are NEVER logged.
"""

import os
import json
import logging
import hashlib
import hmac
import base64
from pathlib import Path
from typing import Optional

from cryptography.hazmat.primitives.asymmetric.ec import (
    ECDH, SECP256R1, generate_private_key, EllipticCurvePrivateKey,
    EllipticCurvePublicKey,
)
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.backends import default_backend
from cryptography.exceptions import InvalidSignature

log = logging.getLogger("aether.pairing.crypto")

KEY_DIR = Path.home() / ".local" / "share" / "aethercontrol" / "keys"
SERVER_KEY_FILE = KEY_DIR / "server_identity.pem"
SERVER_CERT_FILE = KEY_DIR / "server_cert.pem"


def _ensure_key_dir() -> None:
    KEY_DIR.mkdir(parents=True, exist_ok=True)
    KEY_DIR.chmod(0o700)


def generate_server_identity() -> EllipticCurvePrivateKey:
    """Generate a new P-256 server identity key and persist it."""
    _ensure_key_dir()
    private_key = generate_private_key(SECP256R1(), default_backend())
    pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    SERVER_KEY_FILE.write_bytes(pem)
    SERVER_KEY_FILE.chmod(0o600)
    log.info("New server identity key generated")
    return private_key


def load_or_generate_server_identity() -> EllipticCurvePrivateKey:
    """Load existing identity key or generate a new one."""
    _ensure_key_dir()
    if SERVER_KEY_FILE.exists():
        try:
            pem = SERVER_KEY_FILE.read_bytes()
            key = serialization.load_pem_private_key(pem, password=None)
            log.debug("Server identity key loaded")
            return key
        except Exception as exc:
            log.warning("Failed to load identity key (%s); regenerating", exc)
    return generate_server_identity()


def public_key_fingerprint(public_key: EllipticCurvePublicKey) -> str:
    """Return a human-readable SHA-256 fingerprint of a public key."""
    der = public_key.public_bytes(
        serialization.Encoding.DER,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    digest = hashlib.sha256(der).digest()
    # Format as colon-separated hex pairs (like SSH fingerprints)
    return ":".join(f"{b:02X}" for b in digest[:16])  # First 16 bytes


def public_key_to_bytes(public_key: EllipticCurvePublicKey) -> bytes:
    return public_key.public_bytes(
        serialization.Encoding.DER,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )


def public_key_from_bytes(data: bytes) -> EllipticCurvePublicKey:
    return serialization.load_der_public_key(data)


def ecdh_derive_session_key(
    private_key: EllipticCurvePrivateKey,
    peer_public_key: EllipticCurvePublicKey,
    salt: bytes,
    info: bytes = b"aethercontrol-session-v1",
) -> bytes:
    """
    Perform ECDH key exchange and derive a 32-byte session key via HKDF-SHA256.

    Both sides (server and client) must compute this with their own private key
    and the peer's public key; they will derive the same shared secret.
    """
    shared_secret = private_key.exchange(ECDH(), peer_public_key)
    derived = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        info=info,
        backend=default_backend(),
    ).derive(shared_secret)
    return derived


def generate_nonce(length: int = 32) -> bytes:
    """Generate a cryptographically secure random nonce."""
    return os.urandom(length)


def generate_pairing_code() -> str:
    """Generate a 6-digit numeric pairing confirmation code."""
    raw = int.from_bytes(os.urandom(4), "big")
    return str(raw % 1_000_000).zfill(6)


def compute_hmac(key: bytes, data: bytes) -> bytes:
    return hmac.new(key, data, hashlib.sha256).digest()


def verify_hmac(key: bytes, data: bytes, expected: bytes) -> bool:
    actual = compute_hmac(key, data)
    return hmac.compare_digest(actual, expected)


def generate_session_token() -> bytes:
    """Generate a random 32-byte session token."""
    return os.urandom(32)


def token_to_str(token: bytes) -> str:
    return base64.b64encode(token).decode("ascii")


def token_from_str(s: str) -> bytes:
    return base64.b64decode(s)
