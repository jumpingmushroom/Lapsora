from app.config import encrypt, decrypt, Settings


def test_encrypt_decrypt_roundtrip():
    original = "rtsp://user:pass@example.com/stream"
    token = encrypt(original)
    assert token != original
    assert decrypt(token) == original


def test_settings_defaults(monkeypatch):
    # Assert the built-in defaults independent of any LAPSORA_* env vars or .env
    # the suite may be run with (the harness sets LAPSORA_DATA_DIR/DATABASE_URL).
    for var in ("LAPSORA_DATA_DIR", "LAPSORA_DATABASE_URL", "LAPSORA_SECRET_KEY"):
        monkeypatch.delenv(var, raising=False)
    s = Settings(_env_file=None)
    assert s.DATA_DIR == "data"
    assert "sqlite" in s.DATABASE_URL
    assert len(s.SECRET_KEY) > 0
