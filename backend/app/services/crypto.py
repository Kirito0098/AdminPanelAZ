import base64
import hashlib

from cryptography.fernet import Fernet


def _fernet(secret_key: str) -> Fernet:
    key = base64.urlsafe_b64encode(hashlib.sha256(secret_key.encode()).digest())
    return Fernet(key)


def encrypt_secret(plain: str, secret_key: str) -> str:
    return _fernet(secret_key).encrypt(plain.encode()).decode()


def decrypt_secret(encrypted: str, secret_key: str) -> str:
    return _fernet(secret_key).decrypt(encrypted.encode()).decode()
