from app.services import sensor_icons


def test_available_icons_present_on_disk():
    keys = sensor_icons.available_icons()
    assert "thermometer" in keys and "humidity" in keys
    for key in keys:
        assert sensor_icons.icon_path_for(key) is not None, f"missing PNG for {key}"


def test_unknown_or_blank_icon_returns_none():
    assert sensor_icons.icon_path_for("nope") is None
    assert sensor_icons.icon_path_for("") is None
    assert sensor_icons.icon_path_for(None) is None
