import base64
import json
import os
import unittest
from unittest.mock import patch

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from secure_watchlist import decrypt_envelope, load_cloud_watchlist, ROUNDS
from cloud_monitor import prepare_watches


class SecureWatchlistTests(unittest.TestCase):
    def test_roundtrip(self):
        password = 'A very long sample password'
        watches = [{'model': 'iPhone Example', 'email':'test@example.com'}]
        salt = os.urandom(16)
        iv = os.urandom(12)
        key = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=ROUNDS).derive(password.encode())
        data = AESGCM(key).encrypt(iv, json.dumps(watches).encode(), None)
        payload = {'v':1,'salt':base64.b64encode(salt).decode(),'iv':base64.b64encode(iv).decode(),'data':base64.b64encode(data).decode()}
        self.assertEqual(decrypt_envelope(payload, password), watches)
        with self.assertRaisesRegex(ValueError, 'Cannot decrypt'):
            decrypt_envelope(payload, 'wrong password')

    def test_empty_watchlist_can_disable_all(self):
        self.assertEqual(prepare_watches([]), [])

    def test_fallback_to_existing_secret(self):
        with patch('secure_watchlist.SECURE_FILE') as path:
            path.exists.return_value = False
            with patch.dict(os.environ, {'WATCHLIST_JSON': '[{"email":"a@example.com"}]'}):
                self.assertEqual(load_cloud_watchlist()[0]['email'], 'a@example.com')


if __name__ == '__main__':
    unittest.main()
