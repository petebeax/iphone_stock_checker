"""Decrypt browser-managed watchlists with PBKDF2-SHA256 + AES-256-GCM.

Envelope v1 uses base64 fields salt, iv, data, with ciphertext including GCM tag.
An absent encrypted file leaves existing WATCHLIST_JSON workflows untouched.
"""
import base64
import json
import os
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes

ROOT = Path(__file__).resolve().parent
SECURE_FILE = ROOT / 'secure_watchlist.json'
ROUNDS = 250_000


def decrypt_envelope(payload: dict, passphrase: str) -> list[dict]:
    if payload.get('v') != 1:
        raise ValueError('Unsupported encrypted watchlist format')
    if not passphrase:
        raise ValueError('Missing WATCHLIST_PASSPHRASE GitHub Actions secret')
    try:
        salt = base64.b64decode(payload['salt'], validate=True)
        iv = base64.b64decode(payload['iv'], validate=True)
        encrypted = base64.b64decode(payload['data'], validate=True)
        if len(salt) != 16 or len(iv) != 12:
            raise ValueError('Incorrect salt/IV length')
        key = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=ROUNDS).derive(passphrase.encode('utf-8'))
        decoded = json.loads(AESGCM(key).decrypt(iv, encrypted, None))
    except Exception as exc:
        raise ValueError('Cannot decrypt secure_watchlist.json; check WATCHLIST_PASSPHRASE') from exc
    if not isinstance(decoded, list):
        raise ValueError('Encrypted watchlist must contain a JSON list')
    return decoded


def load_cloud_watchlist() -> list[dict]:
    if SECURE_FILE.exists():
        return decrypt_envelope(json.loads(SECURE_FILE.read_text(encoding='utf-8')),
                                os.getenv('WATCHLIST_PASSPHRASE', ''))
    raw = os.getenv('WATCHLIST_JSON', '').strip()
    if not raw:
        raise RuntimeError('Create an encrypted watchlist in GitHub Pages, or configure WATCHLIST_JSON')
    return json.loads(raw)
