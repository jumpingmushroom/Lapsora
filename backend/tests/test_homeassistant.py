import json
import pytest
from app.services import homeassistant as ha


def test_build_sensor_snapshot_merges_config_and_readings():
    sensors = json.dumps([
        {"entity_id": "sensor.temp", "label": "Greenhouse", "unit": "°C", "icon": "thermometer"},
        {"entity_id": "sensor.hum", "label": "Humidity", "unit": "%", "icon": "humidity"},
    ])
    readings = {
        "sensor.temp": {"value": "21.4", "unit": "°C"},
        "sensor.hum": {"value": "62", "unit": "%"},
    }
    out = json.loads(ha.build_sensor_snapshot(sensors, readings))
    assert out["sensor.temp"] == {"value": "21.4", "unit": "°C", "label": "Greenhouse", "icon": "thermometer"}
    assert out["sensor.hum"]["value"] == "62"


def test_build_sensor_snapshot_skips_missing_readings():
    sensors = json.dumps([{"entity_id": "sensor.temp", "label": "T", "unit": "°C", "icon": ""}])
    assert ha.build_sensor_snapshot(sensors, {}) is None


def test_build_sensor_snapshot_unit_falls_back_to_reading():
    sensors = json.dumps([{"entity_id": "sensor.temp", "label": "T", "unit": "", "icon": ""}])
    readings = {"sensor.temp": {"value": "5", "unit": "kWh"}}
    out = json.loads(ha.build_sensor_snapshot(sensors, readings))
    assert out["sensor.temp"]["unit"] == "kWh"


def test_build_sensor_snapshot_handles_bad_json():
    assert ha.build_sensor_snapshot("not json", {}) is None
    assert ha.build_sensor_snapshot(None, {}) is None


@pytest.mark.asyncio
async def test_list_sensor_entities_filters_and_shapes(monkeypatch):
    fake_states = [
        {"entity_id": "sensor.temp", "state": "21.4",
         "attributes": {"friendly_name": "Greenhouse", "unit_of_measurement": "°C", "device_class": "temperature"}},
        {"entity_id": "light.kitchen", "state": "on", "attributes": {"friendly_name": "Kitchen"}},
        {"entity_id": "binary_sensor.door", "state": "off", "attributes": {"friendly_name": "Door"}},
    ]

    async def fake_get_states(base_url, token):
        return fake_states

    monkeypatch.setattr(ha, "get_states", fake_get_states)
    out = await ha.list_sensor_entities("http://x", "tok")
    ids = [e["entity_id"] for e in out]
    assert "sensor.temp" in ids and "binary_sensor.door" in ids
    assert "light.kitchen" not in ids
    temp = next(e for e in out if e["entity_id"] == "sensor.temp")
    assert temp["friendly_name"] == "Greenhouse"
    assert temp["unit"] == "°C"


@pytest.mark.asyncio
async def test_read_sensors_returns_value_and_unit(monkeypatch):
    async def fake_get_states(base_url, token):
        return [{"entity_id": "sensor.temp", "state": "21.4",
                 "attributes": {"unit_of_measurement": "°C"}}]
    monkeypatch.setattr(ha, "get_states", fake_get_states)
    out = await ha.read_sensors("http://x", "tok", ["sensor.temp", "sensor.missing"])
    assert out == {"sensor.temp": {"value": "21.4", "unit": "°C"}}
