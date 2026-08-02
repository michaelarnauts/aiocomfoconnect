"""Pytest configuration and shared fixtures."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from aiocomfoconnect import bridge as bridge_module
from aiocomfoconnect.comfoconnect import ComfoConnect
from aiocomfoconnect.const import ProductId
from aiocomfoconnect.protobuf import zehnder_pb2


@pytest.fixture(autouse=True)
def short_node_discovery_timeout(monkeypatch):
    """Don't wait the full node discovery timeout in tests where no node is announced."""
    monkeypatch.setattr(bridge_module, "NODE_DISCOVERY_TIMEOUT", 0.05)


@pytest.fixture(autouse=True)
def announce_ventilation_node(monkeypatch):
    """Announce a ventilation unit like a real bridge does when the nodes are requested.

    Without this, every test that connects would fail since we don't accept a bridge
    that doesn't tell us where the ventilation unit is. Tests that want to test that
    behaviour patch cmd_node_request again themselves.
    """

    async def cmd_node_request(self):
        node_notification(self, node_id=1, product_id=ProductId.COMFOAIRQ)

    monkeypatch.setattr(ComfoConnect, "cmd_node_request", cmd_node_request)


def node_notification(bridge, node_id, product_id, zone_id=1, mode=zehnder_pb2.CnNodeNotification.NODE_NORMAL):
    """Feed a CnNodeNotification to the bridge, like the bridge would do."""
    msg = zehnder_pb2.CnNodeNotification()
    msg.nodeId = node_id
    msg.productId = product_id
    msg.zoneId = zone_id
    msg.mode = mode
    bridge._process_node_notification(msg)  # pylint: disable=protected-access


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
