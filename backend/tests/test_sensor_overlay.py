import json
from types import SimpleNamespace

from PIL import Image

from app.services import sensor_overlay


def _cap(data: dict | None):
    return SimpleNamespace(sensor_data=json.dumps(data) if data is not None else None)


def test_compute_layout_none_when_no_data():
    assert sensor_overlay.compute_layout([_cap(None), _cap({})]) is None


def test_compute_layout_locks_width_across_varying_values():
    caps = [
        _cap({"sensor.t": {"value": "1", "unit": "°C", "label": "Temp", "icon": "thermometer"}}),
        _cap({"sensor.t": {"value": "888888", "unit": "°C", "label": "Temp", "icon": "thermometer"}}),
    ]
    layout = sensor_overlay.compute_layout(caps)
    assert layout is not None
    assert layout["order"] == ["sensor.t"]
    assert layout["card_w"] > 0 and layout["card_h"] > 0


def test_compute_layout_unions_sensors_first_seen_order():
    caps = [
        _cap({"sensor.a": {"value": "1", "unit": "", "label": "A", "icon": ""}}),
        _cap({"sensor.b": {"value": "2", "unit": "", "label": "B", "icon": ""}}),
    ]
    layout = sensor_overlay.compute_layout(caps)
    assert layout["order"] == ["sensor.a", "sensor.b"]


def test_render_frame_runs_and_keeps_size():
    caps = [_cap({"sensor.t": {"value": "21.4", "unit": "°C", "label": "Greenhouse", "icon": "thermometer"}})]
    layout = sensor_overlay.compute_layout(caps)
    img = Image.new("RGB", (640, 360), (40, 80, 120))
    sensor_overlay.render_frame(img, caps[0], "top-left", layout)
    assert img.size == (640, 360)


def test_render_frame_handles_missing_value_row():
    caps = [
        _cap({"sensor.a": {"value": "1", "unit": "", "label": "A", "icon": ""},
              "sensor.b": {"value": "2", "unit": "", "label": "B", "icon": ""}}),
        _cap({"sensor.a": {"value": "9", "unit": "", "label": "A", "icon": ""}}),
    ]
    layout = sensor_overlay.compute_layout(caps)
    img = Image.new("RGB", (640, 360))
    sensor_overlay.render_frame(img, caps[1], "bottom-right", layout)
    assert img.size == (640, 360)


def test_render_frame_noop_when_layout_none():
    img = Image.new("RGB", (100, 100))
    sensor_overlay.render_frame(img, _cap(None), "top-left", None)
