"""Device unit labels follow the PDO 208 and 224 enumerations."""

import pytest

from aiocomfoconnect.sensors import (
    SENSOR_UNIT_AIRFLOW,
    SENSOR_UNIT_TEMPERATURE,
    SENSORS,
)


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
    """Every documented unit has a distinct, correctly spelled label."""
    assert SENSORS[sensor_id].value_fn(raw) == expected
