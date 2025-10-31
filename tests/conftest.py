"""Pytest configuration and shared fixtures."""

from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture
def mock_connection():
    """Create a mock connection (reader, writer) pair."""
    reader = AsyncMock()
    writer = MagicMock()
    writer.is_closing.return_value = False
    writer.drain = AsyncMock()
    writer.wait_closed = AsyncMock()
    writer.close = MagicMock()
    return (reader, writer)


def create_sensor(name="test_sensor", unit=None, sensor_id=276, sensor_type=1, value_fn=None):
    """Helper function to create a Sensor with correct parameter order."""
    from aiocomfoconnect.sensors import Sensor

    return Sensor(name=name, unit=unit, id=sensor_id, type=sensor_type, value_fn=value_fn)
