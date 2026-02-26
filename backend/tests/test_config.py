from app.config import encrypt, decrypt, Settings


def test_encrypt_decrypt_roundtrip():
    original = "rtsp://admin:secret@192.168.1.100/stream"
    token = encrypt(original)
    assert token != original
    assert decrypt(token) == original


def test_settings_defaults():
    s = Settings()
    assert s.DATA_DIR == "data"
    assert "sqlite" in s.DATABASE_URL
    assert len(s.SECRET_KEY) > 0
