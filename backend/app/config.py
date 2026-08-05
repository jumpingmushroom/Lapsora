"""Application configuration and encryption helpers."""

import base64
import hashlib
import secrets

from cryptography.fernet import Fernet
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LAPSORA_", env_file=".env")

    SECRET_KEY: str = ""
    DATA_DIR: str = "data"
    DATABASE_URL: str = "sqlite:///data/lapsora.db"

    def model_post_init(self, __context: object) -> None:
        if not self.SECRET_KEY:
            self.SECRET_KEY = self._load_or_create_persistent_key()

    def _load_or_create_persistent_key(self) -> str:
        """No env-provided key: reuse a persisted per-install key so encrypted
        data (stream URLs, credentials) survives restarts. Only falls back to an
        ephemeral key when the key file can be neither read nor written."""
        import logging
        import os

        logger = logging.getLogger(__name__)
        key_path = os.path.join(self.DATA_DIR, ".secret_key")

        try:
            if os.path.exists(key_path):
                with open(key_path) as fh:
                    existing = fh.read().strip()
                if existing:
                    return existing
        except OSError:
            logger.warning("Could not read persisted SECRET_KEY at %s", key_path)

        new_key = secrets.token_hex(32)
        try:
            os.makedirs(self.DATA_DIR, exist_ok=True)
            with open(key_path, "w") as fh:
                fh.write(new_key)
            os.chmod(key_path, 0o600)
            logger.warning(
                "LAPSORA_SECRET_KEY not set — generated and persisted a random "
                "key at %s. Set LAPSORA_SECRET_KEY to manage it explicitly.",
                key_path,
            )
        except OSError:
            logger.warning(
                "LAPSORA_SECRET_KEY not set and %s is not writable — using an "
                "ephemeral key. Encrypted data will be unreadable after restart.",
                key_path,
            )
        return new_key


settings = Settings()


def _derive_fernet_key(secret: str) -> bytes:
    """Derive a Fernet-compatible key from the SECRET_KEY via SHA-256 + base64."""
    digest = hashlib.sha256(secret.encode()).digest()
    return base64.urlsafe_b64encode(digest)


def encrypt(plaintext: str) -> str:
    """Encrypt a string and return the Fernet token as a string."""
    f = Fernet(_derive_fernet_key(settings.SECRET_KEY))
    return f.encrypt(plaintext.encode()).decode()


def decrypt(token: str) -> str:
    """Decrypt a Fernet token string back to plaintext."""
    f = Fernet(_derive_fernet_key(settings.SECRET_KEY))
    return f.decrypt(token.encode()).decode()


def decrypt_optional(token: str) -> str | None:
    """Decrypt, or None when the token can't be read under the current key.

    Distinguishes "stored secret is unreadable" (the key was rotated or
    regenerated) from "no secret stored", so callers can tell the user to
    re-enter it instead of failing with a 500."""
    try:
        return decrypt(token)
    except Exception:
        return None
