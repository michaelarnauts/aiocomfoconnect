"""Tests for the sensor definitions and the decoding of sensor values."""

import asyncio

import pytest

from aiocomfoconnect.const import PdoType
from aiocomfoconnect.sensors import (
    SENSOR_CO2_1,
    SENSOR_CO2_8,
    SENSOR_POSTHEATER_PRESENT,
    SENSOR_POSTHEATER_STATE,
    SENSOR_POSTHEATER_TEMPERATURE_BEFORE,
    SENSOR_PRESET_TIMERS,
    SENSOR_UNIT_AIRFLOW,
    SENSOR_UNIT_TEMPERATURE,
    SENSORS,
)
from tests.conftest import create_sensor
from tests.fake_bridge import GO, LOCAL_UUID


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


def test_co2_sensors():
    """The CO2 levels of up to 8 CO2 sensors are pdids 1024 to 1031, in ppm."""
    assert (SENSOR_CO2_1, SENSOR_CO2_8) == (1024, 1031)
    for pdid in range(1024, 1032):
        assert (SENSORS[pdid].type, SENSORS[pdid].unit, SENSORS[pdid].value_fn) == (PdoType.TYPE_CN_UINT16, "ppm", None)


def test_preset_timers_sensor():
    """The running timers of the preset schedule are a UINT32 bit set on pdid 337."""
    sensor = SENSORS[SENSOR_PRESET_TIMERS]
    assert (sensor.id, sensor.name, sensor.type) == (337, "Preset Timers", PdoType.TYPE_CN_UINT32)


def test_postheater_sensors():
    """The ids, types and decoding match what was observed on a unit with a postheater."""
    temperature = SENSORS[SENSOR_POSTHEATER_TEMPERATURE_BEFORE]
    assert (temperature.id, temperature.type, temperature.unit) == (278, PdoType.TYPE_CN_INT16, "°C")
    assert temperature.value_fn(218) == 21.8

    state = SENSORS[SENSOR_POSTHEATER_STATE]
    assert (state.id, state.type, state.unit) == (401, PdoType.TYPE_CN_UINT8, "%")

    present = SENSORS[SENSOR_POSTHEATER_PRESENT]
    assert (present.id, present.type) == (402, PdoType.TYPE_CN_BOOL)


@pytest.mark.parametrize(
    "sensor_id,raw,expected",
    [
        (SENSOR_UNIT_TEMPERATURE, 0, "celsius"),
        (SENSOR_UNIT_TEMPERATURE, 1, "fahrenheit"),
        (SENSOR_UNIT_AIRFLOW, 1, "kgph"),
        (SENSOR_UNIT_AIRFLOW, 2, "lps"),
        (SENSOR_UNIT_AIRFLOW, 3, "m3ph"),
        (SENSOR_UNIT_TEMPERATURE, 255, 255),
        (SENSOR_UNIT_AIRFLOW, 255, 255),
    ],
)
def test_device_unit_labels(sensor_id, raw, expected):
    """Device unit labels follow the PDO 208 and 224 enumerations."""
    assert SENSORS[sensor_id].value_fn(raw) == expected


@pytest.mark.parametrize(
    "pdo_type,data,expected",
    [
        (PdoType.TYPE_CN_UINT8, b"\x80", 128),
        (PdoType.TYPE_CN_UINT16, b"\x00\x80", 32768),
        (PdoType.TYPE_CN_UINT16, b"\xff\xff", 65535),
        (PdoType.TYPE_CN_UINT32, b"\x00\x00\x00\x80", 2147483648),
        (PdoType.TYPE_CN_UINT64, b"\xff" * 8, 2**64 - 1),
        (PdoType.TYPE_CN_INT8, b"\x80", -128),
        (PdoType.TYPE_CN_INT16, b"\xec\xff", -20),
        (PdoType.TYPE_CN_INT32, b"\xfe\xff\xff\xff", -2),
        (PdoType.TYPE_CN_INT64, b"\xff" * 8, -1),
        (PdoType.TYPE_CN_BOOL, b"\xff", -1),
        (PdoType.TYPE_CN_STRING, b"\xff\xff", -1),
        (PdoType.TYPE_CN_TIME, b"\x00\x00\x00\x80", -2147483648),
        (PdoType.TYPE_CN_VERSION, b"\xff\xff\xff\xff", -1),
    ],
)
async def test_sensor_value_signedness(fake_bridge, make_client, pdo_type, data, expected):
    """A sensor value is decoded with the signedness of the sensor's type, also when it arrives before the bridge confirmed the subscription."""
    values = []
    client = make_client(sensor_callback=lambda sensor, value: values.append(value))
    await client.connect(LOCAL_UUID)

    fake_bridge.withhold = {GO.CnRpdoRequestType}
    register_task = asyncio.create_task(client.register_sensor(create_sensor(sensor_id=215, sensor_type=pdo_type)))
    await fake_bridge.wait_for(lambda: fake_bridge.received(GO.CnRpdoRequestType))
    fake_bridge.push_sensor(215, data)
    await client.cmd_time_request()
    fake_bridge.answer_pending()
    await register_task

    assert values == [expected]
