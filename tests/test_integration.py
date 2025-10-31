"""Integration tests for the Bridge and ComfoConnect classes."""

import asyncio
from contextlib import AsyncExitStack
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from aiocomfoconnect.bridge import Bridge
from aiocomfoconnect.comfoconnect import ComfoConnect
from aiocomfoconnect.exceptions import AioComfoConnectNotConnected
from tests.conftest import create_sensor

LOCAL_UUID = "00000000000000000000000000000001"


class MockBridge:
    """Mock bridge for testing complete scenarios."""

    def __init__(self):
        self.reader = AsyncMock()
        self.writer = MagicMock()
        self.writer.is_closing.return_value = False
        self.writer.drain = AsyncMock()
        self.writer.wait_closed = AsyncMock()
        self.disconnect_after = None
        self.connection_count = 0

    async def open_connection(self, *args, **kwargs):
        """Mock open_connection that can simulate disconnects."""
        self.connection_count += 1
        return (self.reader, self.writer)

    async def read_messages_impl(self, bridge_instance=None):
        """Mock read_messages that can disconnect after a delay."""
        if self.disconnect_after:
            await asyncio.sleep(self.disconnect_after)
            raise AioComfoConnectNotConnected("Simulated disconnect")
        else:
            await asyncio.sleep(100)  # Keep running


class TestIntegrationScenarios:
    """Test complete integration scenarios."""

    @pytest.mark.asyncio
    async def test_complete_connection_lifecycle(self):
        """Test a complete connection, use, and disconnection lifecycle."""
        mock = MockBridge()

        bridge = Bridge("192.168.1.100", "00000000000000000000000000000001")

        with patch("asyncio.open_connection", side_effect=mock.open_connection):
            with patch.object(bridge, "_read_messages", new=AsyncMock(side_effect=mock.read_messages_impl)):
                # Connect
                await bridge.connect(LOCAL_UUID)
                assert bridge.is_connected()
                assert mock.connection_count == 1

                # Verify we can check connection state
                assert bridge.is_connected()

                # Disconnect
                await bridge.disconnect()
                assert not bridge.is_connected()

    @pytest.mark.asyncio
    async def test_reconnection_after_disconnect(self):
        """Test automatic reconnection after connection loss."""
        mock = MockBridge()
        mock.disconnect_after = 0.2  # Disconnect after 0.2 seconds

        cc = ComfoConnect(
            "192.168.1.100",
            "00000000000000000000000000000001",
            sensor_delay=0,
        )

        with patch("asyncio.open_connection", side_effect=mock.open_connection):
            with patch.object(cc, "cmd_start_session", AsyncMock()):
                with patch.object(cc, "_read_messages", new=AsyncMock(side_effect=mock.read_messages_impl)):
                    # Connect
                    await cc.connect(LOCAL_UUID)
                    assert cc.is_connected()

                    # Wait for disconnect and reconnect
                    await asyncio.sleep(1.5)

                    # Should have reconnected
                    assert mock.connection_count >= 2

                    # Clean up
                    await cc.disconnect()


@pytest.mark.asyncio
async def test_sensor_registration():
    """Test sensor registration after connection."""
    mock = MockBridge()

    async def mock_rpdo(pdid, sensor_type):
        await asyncio.sleep(0.05)
        return b"\x01\x00\x00\x00"

    cc = ComfoConnect(
        "192.168.1.100",
        "00000000000000000000000000000001",
        sensor_delay=0,
    )

    # Register sensors before connecting
    sensor1 = create_sensor(name="temp", sensor_id=276, sensor_type=1)
    sensor2 = create_sensor(name="humidity", sensor_id=277, sensor_type=1)

    with patch("asyncio.open_connection", side_effect=mock.open_connection):
        with patch.object(cc, "cmd_start_session", AsyncMock()):
            with patch.object(cc, "cmd_rpdo_request", side_effect=mock_rpdo):
                with patch.object(cc, "_read_messages", new=AsyncMock(side_effect=mock.read_messages_impl)):
                    # Connect
                    await cc.connect(LOCAL_UUID)

                    # Register sensors
                    await cc.register_sensor(sensor1)
                    await cc.register_sensor(sensor2)

                    # Verify sensors are registered
                    assert 276 in cc._sensors
                    assert 277 in cc._sensors

                    # Simulate disconnect by triggering it
                    mock.disconnect_after = 0.1
                    await asyncio.sleep(1.5)

                    # Reset for next connection
                    mock.disconnect_after = None

                    # All should succeed
                    assert cc.is_connected()

                # Clean up
                await cc.disconnect()


@pytest.mark.asyncio
async def test_sensor_callbacks_work():
    """Test that sensor callbacks are properly called."""
    mock = MockBridge()
    sensor_values = []

    def sensor_callback(sensor, value):
        sensor_values.append((sensor.id, value))

    cc = ComfoConnect(
        "192.168.1.100",
        "00000000000000000000000000000001",
        sensor_callback=sensor_callback,
        sensor_delay=0,
    )

    with patch("asyncio.open_connection", side_effect=mock.open_connection):
        with patch.object(cc, "cmd_start_session", AsyncMock()):
            with patch.object(cc, "cmd_rpdo_request", AsyncMock()):
                with patch.object(cc, "_read_messages", new=AsyncMock(side_effect=mock.read_messages_impl)):
                    # Connect
                    await cc.connect(LOCAL_UUID)

                    # Register sensor
                    sensor = create_sensor(name="temp", sensor_id=276, sensor_type=1)
                    await cc.register_sensor(sensor)

                    # Simulate sensor data
                    cc._sensor_callback(276, 1234)

                    # Verify callback was called
                    assert len(sensor_values) == 1
                    assert sensor_values[0] == (276, 1234)

                    # Clean up
                    await cc.disconnect()


@pytest.mark.asyncio
async def test_alarm_callbacks_work():
    """Test that alarm callbacks are properly called."""
    mock = MockBridge()
    alarms = []

    def alarm_callback(node_id, errors):
        alarms.append((node_id, errors))

    cc = ComfoConnect(
        "192.168.1.100",
        "00000000000000000000000000000001",
        alarm_callback=alarm_callback,
        sensor_delay=0,
    )

    with patch("asyncio.open_connection", side_effect=mock.open_connection):
        with patch.object(cc, "cmd_start_session", AsyncMock()):
            with patch.object(cc, "_read_messages", new=AsyncMock(side_effect=mock.read_messages_impl)):
                # Connect
                await cc.connect(LOCAL_UUID)

                # Simulate alarm
                mock_alarm = Mock()
                mock_alarm.swProgramVersion = 3222278145  # Firmware > 1.4.0
                # Set bit 52 which corresponds to "The supply air fan has a malfunction"
                # Byte index 6, bit 4 (52 = 6*8 + 4)
                mock_alarm.errors = b"\x00\x00\x00\x00\x00\x00\x10\x00"

                cc._alarm_callback(1, mock_alarm)

                # Verify callback was called
                assert len(alarms) == 1
                assert alarms[0][0] == 1
                assert isinstance(alarms[0][1], dict)

                # Clean up
                await cc.disconnect()


@pytest.mark.asyncio
async def test_graceful_shutdown():
    """Test graceful shutdown stops reconnection."""
    mock = MockBridge()

    cc = ComfoConnect(
        "192.168.1.100",
        "00000000000000000000000000000001",
        sensor_delay=0,
    )

    with patch("asyncio.open_connection", side_effect=mock.open_connection):
        with patch.object(cc, "cmd_start_session", AsyncMock()):
            with patch.object(cc, "_read_messages", new=AsyncMock(side_effect=mock.read_messages_impl)):
                # Connect
                await cc.connect(LOCAL_UUID)
                assert cc.is_connected()

                initial_count = mock.connection_count

                # Disconnect
                await cc.disconnect()
                assert not cc.is_connected()
                assert cc._is_stopping

                # Wait a bit to ensure no reconnection happens
                await asyncio.sleep(1)

                # Should not have reconnected
                assert mock.connection_count == initial_count


@pytest.mark.asyncio
async def test_concurrent_operations():
    """Test that concurrent operations work correctly."""
    mock = MockBridge()

    cc = ComfoConnect(
        "192.168.1.100",
        "00000000000000000000000000000001",
        sensor_delay=0,
    )

    with patch("asyncio.open_connection", side_effect=mock.open_connection):
        with patch.object(cc, "cmd_start_session", AsyncMock()):
            with patch.object(cc, "_read_messages", new=AsyncMock(side_effect=mock.read_messages_impl)):
                # Connect
                await cc.connect(LOCAL_UUID)

                # Register multiple sensors concurrently
                with patch.object(cc, "cmd_rpdo_request", AsyncMock()):
                    sensors = [create_sensor(name=f"sensor_{i}", sensor_id=i, sensor_type=1) for i in range(10)]

                    await asyncio.gather(*[cc.register_sensor(s) for s in sensors])

                    # All should be registered
                    assert len(cc._sensors) == 10

                # Clean up
                await cc.disconnect()


@pytest.mark.asyncio
async def test_stress_reconnection():
    """Test rapid reconnections."""
    connection_count = 0

    async def flaky_connection(*args, **kwargs):
        nonlocal connection_count
        connection_count += 1
        reader = AsyncMock()
        writer = MagicMock()
        writer.is_closing.return_value = False
        writer.drain = AsyncMock()
        writer.wait_closed = AsyncMock()
        return (reader, writer)

    async def quick_disconnect():
        # Disconnect quickly
        await asyncio.sleep(0.05)
        raise AioComfoConnectNotConnected("Quick disconnect")

    cc = ComfoConnect(
        "192.168.1.100",
        "00000000000000000000000000000001",
        sensor_delay=0,
    )

    with patch("asyncio.open_connection", side_effect=flaky_connection):
        with patch.object(cc, "cmd_start_session", AsyncMock()):
            with patch.object(cc, "_read_messages", side_effect=quick_disconnect):
                # Connect
                await cc.connect(LOCAL_UUID)

                # Wait for multiple reconnections
                await asyncio.sleep(2.5)

                # Should have attempted multiple connections
                assert connection_count >= 3

                # Clean up
                await cc.disconnect()
