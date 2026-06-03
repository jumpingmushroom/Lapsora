from app.services.weather import WMO_CODES
from app.services import weather_icons as wi


def test_every_wmo_code_resolves_to_existing_icon():
    for code in WMO_CODES:
        for is_day in (True, False):
            path = wi.icon_path_for(code, is_day)
            assert path is not None, f"missing icon for code={code} is_day={is_day}"


def test_clear_day_vs_night():
    assert wi.icon_name_for(0, True) == "clear-day"
    assert wi.icon_name_for(0, False) == "clear-night"


def test_null_is_day_falls_back_to_day():
    assert wi.icon_name_for(0, None) == "clear-day"


def test_rain_has_no_day_night_variant():
    assert wi.icon_name_for(61, True) == "rain"
    assert wi.icon_name_for(61, False) == "rain"


def test_unknown_code_uses_fallback():
    assert wi.icon_name_for(123456, True) == "overcast"
    assert wi.icon_path_for(123456, True) is not None
