"""Tests for credential encryption/decryption."""
from app.services.crypto_service import encrypt_credentials, decrypt_credentials


class TestCryptoService:
    def test_roundtrip(self):
        creds = {"username": "admin", "password": "secret123", "token": "abc-def"}
        encrypted = encrypt_credentials(creds)
        assert isinstance(encrypted, bytes)
        assert encrypted != b""
        decrypted = decrypt_credentials(encrypted)
        assert decrypted == creds

    def test_different_encryptions(self):
        creds = {"key": "value"}
        enc1 = encrypt_credentials(creds)
        enc2 = encrypt_credentials(creds)
        # Fernet uses random IV, so different encryptions differ
        assert enc1 != enc2
        # But both decrypt to the same value
        assert decrypt_credentials(enc1) == decrypt_credentials(enc2)

    def test_empty_credentials(self):
        creds = {}
        encrypted = encrypt_credentials(creds)
        assert decrypt_credentials(encrypted) == {}

    def test_nested_credentials(self):
        creds = {"oauth": {"client_id": "abc", "client_secret": "xyz"}, "scopes": ["read", "write"]}
        encrypted = encrypt_credentials(creds)
        assert decrypt_credentials(encrypted) == creds
