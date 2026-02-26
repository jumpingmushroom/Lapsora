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
            self.SECRET_KEY = secrets.token_hex(32)


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
