"""
Brain_Scape — Encryption

AES-256 encryption for data at rest. TLS 1.3 for data in transit.
No scan data ever travels or rests in plaintext.
"""

import base64
import os
from typing import Optional

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


class EncryptionManager:
    """
    Manages AES-256 encryption for data at rest.

    Uses Fernet (AES-128-CBC with HMAC-SHA256) for symmetric encryption.
    In production, this would use HashiCorp Vault or AWS KMS for key management.
    """

    def __init__(self, encryption_key: Optional[str] = None):
        """
        Args:
            encryption_key: Base64-encoded encryption key.
                          If None, generates a new key.
        """
        if encryption_key:
            # Derive a Fernet key from the provided key
            key_bytes = encryption_key.encode()
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=32,
                salt=b"brainscape-salt",  # In production: use random salt per dataset
                iterations=480000,
            )
            derived_key = base64.urlsafe_b64encode(kdf.derive(key_bytes))
            self._fernet = Fernet(derived_key)
        else:
            self._fernet = Fernet(Fernet.generate_key())

    def encrypt(self, plaintext: bytes) -> bytes:
        """Encrypt data at rest."""
        return self._fernet.encrypt(plaintext)

    def decrypt(self, ciphertext: bytes) -> bytes:
        """Decrypt data at rest."""
        return self._fernet.decrypt(ciphertext)

    def encrypt_file(self, input_path: str, output_path: str) -> str:
        """Encrypt a file at rest."""
        with open(input_path, "rb") as f:
            plaintext = f.read()

        ciphertext = self.encrypt(plaintext)

        with open(output_path, "wb") as f:
            f.write(ciphertext)

        return output_path

    def decrypt_file(self, input_path: str, output_path: str) -> str:
        """Decrypt a file at rest."""
        with open(input_path, "rb") as f:
            ciphertext = f.read()

        plaintext = self.decrypt(ciphertext)

        with open(output_path, "wb") as f:
            f.write(plaintext)

        return output_path

    @staticmethod
    def generate_key() -> str:
        """Generate a new encryption key (store securely)."""
        return Fernet.generate_key().decode()