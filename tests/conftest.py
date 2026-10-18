"""Pytest configuration and shared fixtures."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from aiocomfoconnect import bridge as bridge_module
from aiocomfoconnect import comfoconnect as comfoconnect_module
from aiocomfoconnect.bridge import Bridge
from aiocomfoconnect.comfoconnect import ComfoConnect
from aiocomfoconnect.protobuf import zehnder_pb2
from tests.fake_bridge import BRIDGE_UUID, FakeBridge


@pytest.fixture(autouse=True)
def short_delays(monkeypatch):
    """Don't wait for the real node discovery timeout and reconnect back-off in tests."""
    monkeypatch.setattr(bridge_module, "NODE_DISCOVERY_TIMEOUT", 0.05)
    monkeypatch.setattr(comfoconnect_module, "RECONNECT_DELAY", 0.01)
    monkeypatch.setattr(comfoconnect_module, "RECONNECT_RETRY_DELAY", 0.01)
    monkeypatch.setattr(comfoconnect_module, "RECONNECT_SESSION_CLOSED_DELAY", 0.01)


@pytest.fixture
async def fake_bridge(monkeypatch):
    """A fake bridge on localhost that the Bridge and ComfoConnect classes connect to."""
    async with FakeBridge() as fake:
        monkeypatch.setattr(Bridge, "PORT", fake.port)
        # The fake bridge answers right away, so a request it doesn't answer can time out quickly.
        monkeypatch.setattr(bridge_module, "TIMEOUT", 0.2)
        yield fake


@pytest.fixture
async def make_client(fake_bridge):  # pylint: disable=redefined-outer-name,unused-argument
    """Create ComfoConnect clients for the fake bridge, and disconnect them at the end of the test."""
    clients = []

    def factory(**kwargs) -> ComfoConnect:
        kwargs.setdefault("sensor_delay", 0)
        kwargs.setdefault("connect_timeout", 1)
        client = ComfoConnect("127.0.0.1", BRIDGE_UUID, **kwargs)
        clients.append(client)
        return client

    yield factory

    for client in clients:
        await client.disconnect()


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
