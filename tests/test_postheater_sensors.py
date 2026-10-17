"""The postheater PDOs have named constants and decode to their units."""

from aiocomfoconnect.const import PdoType
from aiocomfoconnect.sensors import (
    SENSOR_POSTHEATER_PRESENT,
    SENSOR_POSTHEATER_STATE,
    SENSOR_POSTHEATER_TEMPERATURE_BEFORE,
    SENSORS,
)


def test_postheater_sensors():
    """The ids, types and decoding match what was observed on a unit with a postheater."""
    temperature = SENSORS[SENSOR_POSTHEATER_TEMPERATURE_BEFORE]
    assert (temperature.id, temperature.type, temperature.unit) == (278, PdoType.TYPE_CN_INT16, "°C")
    assert temperature.value_fn(218) == 21.8

    state = SENSORS[SENSOR_POSTHEATER_STATE]
    assert (state.id, state.type, state.unit) == (401, PdoType.TYPE_CN_UINT8, "%")

    present = SENSORS[SENSOR_POSTHEATER_PRESENT]
    assert (present.id, present.type) == (402, PdoType.TYPE_CN_BOOL)
    assert present.value_fn(1) is True
