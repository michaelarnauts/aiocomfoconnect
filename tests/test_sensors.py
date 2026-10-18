"""Tests for the sensor definitions."""

import pytest

from aiocomfoconnect.const import PdoType
from aiocomfoconnect.sensors import SENSORS

# Every sensor: its id, name, unit, type, and its value for the raw values 0, 1 and 75.
SENSOR_SNAPSHOT = [
    (16, "Device State", None, PdoType.TYPE_CN_UINT8, (0, 1, 75)),
    (18, "Changing filters", None, PdoType.TYPE_CN_UINT8, (0, 1, 75)),
    (33, "sensor_33", None, PdoType.TYPE_CN_UINT8, (0, 1, 75)),
    (37, "sensor_37", None, PdoType.TYPE_CN_UINT8, (0, 1, 75)),
    (49, "Operating Mode (preset timer)", None, PdoType.TYPE_CN_UINT8, (0, 1, 75)),
    (53, "sensor_53", None, PdoType.TYPE_CN_UINT8, (0, 1, 75)),
    (54, "Supply Fan Mode (active timer)", None, PdoType.TYPE_CN_UINT8, (0, 1, 75)),
    (55, "Exhaust Fan Mode (active timer)", None, PdoType.TYPE_CN_UINT8, (0, 1, 75)),
    (56, "Operating Mode", None, PdoType.TYPE_CN_UINT8, (0, 1, 75)),
    (65, "Fan Speed", None, PdoType.TYPE_CN_UINT8, (0, 1, 75)),
    (66, "Bypass Activation State", None, PdoType.TYPE_CN_UINT8, (0, 1, 75)),
    (67, "Temperature Profile Mode", None, PdoType.TYPE_CN_UINT8, (0, 1, 75)),
    (70, "Supply Fan Mode", None, PdoType.TYPE_CN_UINT8, (0, 1, 75)),
    (71, "Exhaust Fan Mode", None, PdoType.TYPE_CN_UINT8, (0, 1, 75)),
    (81, "Fan Speed Next Change", None, PdoType.TYPE_CN_UINT32, (0, 1, 75)),
    (82, "Bypass Next Change", None, PdoType.TYPE_CN_UINT32, (0, 1, 75)),
    (85, "sensor_85", None, PdoType.TYPE_CN_UINT32, (0, 1, 75)),
    (86, "Supply Fan Next Change", None, PdoType.TYPE_CN_UINT32, (0, 1, 75)),
    (87, "Exhaust Fan Next Change", None, PdoType.TYPE_CN_UINT32, (0, 1, 75)),
    (117, "Exhaust Fan Duty", "%", PdoType.TYPE_CN_UINT8, (0, 1, 75)),
    (118, "Supply Fan Duty", "%", PdoType.TYPE_CN_UINT8, (0, 1, 75)),
    (119, "Exhaust Fan Flow", "m³/h", PdoType.TYPE_CN_UINT16, (0, 1, 75)),
    (120, "Supply Fan Flow", "m³/h", PdoType.TYPE_CN_UINT16, (0, 1, 75)),
    (121, "Exhaust Fan Speed", "rpm", PdoType.TYPE_CN_UINT16, (0, 1, 75)),
    (122, "Supply Fan Speed", "rpm", PdoType.TYPE_CN_UINT16, (0, 1, 75)),
    (128, "Power Usage", "W", PdoType.TYPE_CN_UINT16, (0, 1, 75)),
    (129, "Power Usage (year)", "kWh", PdoType.TYPE_CN_UINT16, (0, 1, 75)),
    (130, "Power Usage (total)", "kWh", PdoType.TYPE_CN_UINT16, (0, 1, 75)),
    (144, "Preheater Power Usage (year)", "kWh", PdoType.TYPE_CN_UINT16, (0, 1, 75)),
    (145, "Preheater Power Usage (total)", "kWh", PdoType.TYPE_CN_UINT16, (0, 1, 75)),
    (146, "Preheater Power Usage", "W", PdoType.TYPE_CN_UINT16, (0, 1, 75)),
    (176, "RF Pairing Mode", None, PdoType.TYPE_CN_UINT8, (0, 1, 75)),
    (192, "Days remaining to replace the filter", None, PdoType.TYPE_CN_UINT16, (0, 1, 75)),
    (208, "Device Temperature Unit", None, PdoType.TYPE_CN_UINT8, ("celsius", "fahrenheit", 75)),
    (209, "Running Mean Outdoor Temperature (RMOT)", "°C", PdoType.TYPE_CN_INT16, (0.0, 0.1, 7.5)),
    (210, "Heating Season is active", None, PdoType.TYPE_CN_BOOL, (False, True, True)),
    (211, "Cooling Season is active", None, PdoType.TYPE_CN_BOOL, (False, True, True)),
    (212, "Target Temperature", "°C", PdoType.TYPE_CN_INT16, (0.0, 0.1, 7.5)),
    (213, "Avoided Heating Power Usage", "W", PdoType.TYPE_CN_UINT16, (0, 1, 75)),
    (214, "Avoided Heating Power Usage (year)", "kWh", PdoType.TYPE_CN_UINT16, (0, 1, 75)),
    (215, "Avoided Heating Power Usage (total)", "kWh", PdoType.TYPE_CN_UINT16, (0, 1, 75)),
    (216, "Avoided Cooling Power Usage", "W", PdoType.TYPE_CN_UINT16, (0, 1, 75)),
    (217, "Avoided Cooling Power Usage (year)", "kWh", PdoType.TYPE_CN_UINT16, (0, 1, 75)),
    (218, "Avoided Cooling Power Usage (total)", "kWh", PdoType.TYPE_CN_UINT16, (0, 1, 75)),
    (219, "sensor_219", None, PdoType.TYPE_CN_UINT16, (0, 1, 75)),
    (220, "Preheated Outdoor Air Temperature (?)", "°C", PdoType.TYPE_CN_INT16, (0.0, 0.1, 7.5)),
    (221, "Supply Air Temperature", "°C", PdoType.TYPE_CN_INT16, (0.0, 0.1, 7.5)),
    (224, "Device Airflow Unit", None, PdoType.TYPE_CN_UINT8, (0, "kgph", 75)),
    (225, "Sensor based ventilation mode", None, PdoType.TYPE_CN_UINT8, (0, 1, 75)),
    (226, "Fan Speed (modulated)", None, PdoType.TYPE_CN_UINT16, (0, 1, 75)),
    (227, "Bypass State", "%", PdoType.TYPE_CN_UINT8, (0, 1, 75)),
    (228, "frostprotection_unbalance", None, PdoType.TYPE_CN_UINT8, (0, 1, 75)),
    (230, "Airflow constraints", None, PdoType.TYPE_CN_INT64, (None, None, None)),
    (274, "Extract Air Temperature", "°C", PdoType.TYPE_CN_INT16, (0.0, 0.1, 7.5)),
    (275, "Exhaust Air Temperature", "°C", PdoType.TYPE_CN_INT16, (0.0, 0.1, 7.5)),
    (276, "Outdoor Air Temperature", "°C", PdoType.TYPE_CN_INT16, (0.0, 0.1, 7.5)),
    (277, "Outdoor Air Temperature (?)", "°C", PdoType.TYPE_CN_INT16, (0.0, 0.1, 7.5)),
    (278, "Temperature before Postheater", "°C", PdoType.TYPE_CN_INT16, (0.0, 0.1, 7.5)),
    (290, "Extract Air Humidity", "%", PdoType.TYPE_CN_UINT8, (0, 1, 75)),
    (291, "Exhaust Air Humidity", "%", PdoType.TYPE_CN_UINT8, (0, 1, 75)),
    (292, "Outdoor Air Humidity", "%", PdoType.TYPE_CN_UINT8, (0, 1, 75)),
    (293, "Outdoor Air Humidity (after preheater)", "%", PdoType.TYPE_CN_UINT8, (0, 1, 75)),
    (294, "Supply Air Humidity", "%", PdoType.TYPE_CN_UINT8, (0, 1, 75)),
    (321, "sensor_321", None, PdoType.TYPE_CN_UINT16, (0, 1, 75)),
    (325, "sensor_325", None, PdoType.TYPE_CN_UINT16, (0, 1, 75)),
    (337, "sensor_337", None, PdoType.TYPE_CN_UINT32, (0, 1, 75)),
    (338, "Bypass Override", None, PdoType.TYPE_CN_UINT32, (0, 1, 75)),
    (341, "sensor_341", None, PdoType.TYPE_CN_UINT32, (0, 1, 75)),
    (342, "Supply Fan Mode (running timers)", None, PdoType.TYPE_CN_UINT32, (0, 1, 75)),
    (343, "Exhaust Fan Mode (running timers)", None, PdoType.TYPE_CN_UINT32, (0, 1, 75)),
    (369, "Analog Input 1", "V", PdoType.TYPE_CN_UINT8, (0.0, 0.1, 7.5)),
    (370, "Analog Input 2", "V", PdoType.TYPE_CN_UINT8, (0.0, 0.1, 7.5)),
    (371, "Analog Input 3", "V", PdoType.TYPE_CN_UINT8, (0.0, 0.1, 7.5)),
    (372, "Analog Input 4", "V", PdoType.TYPE_CN_UINT8, (0.0, 0.1, 7.5)),
    (384, "sensor_384", None, PdoType.TYPE_CN_INT16, (0.0, 0.1, 7.5)),
    (386, "sensor_386", None, PdoType.TYPE_CN_BOOL, (False, True, True)),
    (400, "sensor_400", None, PdoType.TYPE_CN_INT16, (0.0, 0.1, 7.5)),
    (401, "Postheater State", "%", PdoType.TYPE_CN_UINT8, (0, 1, 75)),
    (402, "Postheater Present", None, PdoType.TYPE_CN_BOOL, (False, True, True)),
    (416, "ComfoFond Outdoor Air Temperature", "°C", PdoType.TYPE_CN_INT16, (0.0, 0.1, 7.5)),
    (417, "ComfoFond Ground Temperature", "°C", PdoType.TYPE_CN_INT16, (0.0, 0.1, 7.5)),
    (418, "ComfoFond GHE State Percentage", "%", PdoType.TYPE_CN_UINT8, (0, 1, 75)),
    (419, "ComfoFond GHE Present", None, PdoType.TYPE_CN_BOOL, (False, True, True)),
    (784, "ComfoCool State", None, PdoType.TYPE_CN_UINT8, (0, 1, 75)),
    (785, "sensor_785", None, PdoType.TYPE_CN_BOOL, (False, True, True)),
    (802, "ComfoCool Condensor Temperature", "°C", PdoType.TYPE_CN_INT16, (0.0, 0.1, 7.5)),
    (4145, "ComfoClime TPMA Temperature", "°C", PdoType.TYPE_CN_INT16, (0.0, 0.1, 7.5)),
    (4148, "ComfoClime Target Temperature", "°C", PdoType.TYPE_CN_INT16, (0.0, 0.1, 7.5)),
    (4149, "ComfoClime Device Mode", None, PdoType.TYPE_CN_UINT8, (0, 1, 75)),
    (4151, "ComfoClime Comfort Temperature", "°C", PdoType.TYPE_CN_INT16, (0.0, 0.1, 7.5)),
    (4154, "ComfoClime Indoor Temperature", "°C", PdoType.TYPE_CN_INT16, (0.0, 0.1, 7.5)),
    (4193, "ComfoClime Supply Air Temperature", "°C", PdoType.TYPE_CN_INT16, (0.0, 0.1, 7.5)),
    (4194, "ComfoClime Exhaust Air Temperature", "°C", PdoType.TYPE_CN_INT16, (0.0, 0.1, 7.5)),
    (4195, "ComfoClime Supply Coil Temperature", "°C", PdoType.TYPE_CN_INT16, (0.0, 0.1, 7.5)),
    (4196, "ComfoClime Exhaust Coil Temperature", "°C", PdoType.TYPE_CN_INT16, (0.0, 0.1, 7.5)),
    (4197, "ComfoClime Compressor Temperature", "°C", PdoType.TYPE_CN_INT16, (0.0, 0.1, 7.5)),
    (4198, "ComfoClime Heat Pump Duty", "%", PdoType.TYPE_CN_UINT8, (0, 1, 75)),
    (4201, "ComfoClime Power Usage", "W", PdoType.TYPE_CN_UINT16, (0, 1, 75)),
    (4202, "sensor_4202", None, PdoType.TYPE_CN_UINT16, (0, 1, 75)),
    (4203, "sensor_4203", None, PdoType.TYPE_CN_UINT16, (0, 1, 75)),
    (4204, "sensor_4204", None, PdoType.TYPE_CN_UINT16, (0, 1, 75)),
    (4205, "sensor_4205", None, PdoType.TYPE_CN_UINT16, (0, 1, 75)),
    (4206, "sensor_4206", None, PdoType.TYPE_CN_UINT16, (0, 1, 75)),
    (4207, "sensor_4207", None, PdoType.TYPE_CN_UINT16, (0, 1, 75)),
    (4208, "sensor_4208", None, PdoType.TYPE_CN_UINT16, (0, 1, 75)),
]


def test_sensors_snapshot():
    """The sensor table has exactly these sensors, in this order, with this metadata and these values."""
    actual = [
        (sensor_id, sensor.name, sensor.unit, sensor.type, tuple(sensor.value_fn(raw) if sensor.value_fn else raw for raw in (0, 1, 75))) for sensor_id, sensor in SENSORS.items()
    ]
    assert actual == SENSOR_SNAPSHOT


@pytest.mark.parametrize("sensor_id", list(SENSORS))
def test_sensor_id_is_its_key(sensor_id):
    """Each sensor is stored under its own id."""
    assert SENSORS[sensor_id].id == sensor_id


def test_sensor_names_are_unique():
    """No two sensors share a name."""
    names = [sensor.name for sensor in SENSORS.values()]
    assert len(names) == len(set(names))


@pytest.mark.parametrize("sensor", [sensor for sensor in SENSORS.values() if sensor.type == PdoType.TYPE_CN_BOOL], ids=lambda sensor: str(sensor.id))
def test_bool_sensors_return_a_bool(sensor):
    """A BOOL sensor returns True or False."""
    assert sensor.value_fn(1) is True


@pytest.mark.parametrize("sensor", [sensor for sensor in SENSORS.values() if sensor.value_fn and sensor.value_fn(75) == 7.5], ids=lambda sensor: str(sensor.id))
def test_scaled_sensors_have_a_unit(sensor):
    """A sensor that is scaled by 10 has a unit, unless we don't know what it measures."""
    assert sensor.unit is not None or sensor.name.startswith("sensor_")
