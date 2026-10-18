"""Tests for the sensor definitions."""

from aiocomfoconnect.const import PdoType
from aiocomfoconnect.sensors import SENSORS


def test_sensor_names_are_unique():
    """No two sensors share a name."""
    names = [sensor.name for sensor in SENSORS.values()]
    assert len(names) == len(set(names))


def test_bool_sensors_return_a_bool():
    """A BOOL sensor returns True or False."""
    assert all(sensor.value_fn(1) is True for sensor in SENSORS.values() if sensor.type == PdoType.TYPE_CN_BOOL)


def test_scaled_sensors_have_a_unit():
    """A sensor that is scaled by 10 has a unit, unless we don't know what it measures (sensor_<id>)."""
    scaled = [sensor for sensor in SENSORS.values() if sensor.value_fn and sensor.value_fn(75) == 7.5]
    assert scaled and all(sensor.unit or sensor.name.startswith("sensor_") for sensor in scaled)
