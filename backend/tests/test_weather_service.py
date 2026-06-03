from unittest.mock import patch, MagicMock

import app.services.weather as weather


def _resp(payload):
    m = MagicMock()
    m.json.return_value = payload
    m.raise_for_status.return_value = None
    return m


def test_get_current_weather_returns_is_day():
    weather._cache.clear()
    payload = {"current": {"temperature_2m": 12.5, "weather_code": 61, "is_day": 0}}

    class FakeClient:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def get(self, *a, **k): return _resp(payload)

    with patch.object(weather.httpx, "AsyncClient", FakeClient):
        import asyncio
        result = asyncio.run(weather.get_current_weather(59.3, 18.0))

    assert result == (12.5, 61, False)


def test_get_current_weather_is_day_true():
    weather._cache.clear()
    payload = {"current": {"temperature_2m": 20.0, "weather_code": 0, "is_day": 1}}

    class FakeClient:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def get(self, *a, **k): return _resp(payload)

    with patch.object(weather.httpx, "AsyncClient", FakeClient):
        import asyncio
        result = asyncio.run(weather.get_current_weather(59.3, 18.0))

    assert result == (20.0, 0, True)


def test_capture_model_stores_is_day(db):
    from app.models import Capture, Profile, Stream

    stream = Stream(name="TestStream", url="rtsp://localhost/test")
    db.add(stream)
    db.flush()

    profile = Profile(stream_id=stream.id, name="TestProfile")
    db.add(profile)
    db.flush()

    cap = Capture(
        profile_id=profile.id,
        file_path="a.jpg",
        file_size=1,
        width=1,
        height=1,
        is_hdr=False,
        weather_temp=5.0,
        weather_code=61,
        weather_is_day=False,
    )
    db.add(cap)
    db.flush()
    db.refresh(cap)

    assert cap.weather_is_day is False
