"""Tests for the ComfoConnect class."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, Mock, call, patch

import pytest

from aiocomfoconnect.comfoconnect import ComfoConnect
from aiocomfoconnect.exceptions import (
    AioComfoConnectNotConnected,
    AioComfoConnectTimeout,
    ComfoConnectNotAllowed,
)
from tests.conftest import create_sensor

LOCAL_UUID = "00000000000000000000000000000001"


class TestComfoConnect:
    """Test the ComfoConnect class."""

    @pytest.fixture
    def comfoconnect(self):
        """Create a ComfoConnect instance for testing."""
        return ComfoConnect(
            "192.168.1.100",
            "00000000000000000000000000000001",
            sensor_callback=Mock(),
            alarm_callback=Mock(),
            sensor_delay=0,  # Disable sensor delay for tests
            connect_timeout=1,  # Short timeout for tests
        )

    @pytest.mark.asyncio
    async def test_init(self, comfoconnect):
        """Test ComfoConnect initialization."""
        assert comfoconnect.host == "192.168.1.100"
        assert comfoconnect.uuid == "00000000000000000000000000000001"
        assert comfoconnect.sensor_delay == 0
        assert comfoconnect._sensors == {}
        assert comfoconnect._sensors_values == {}
        assert comfoconnect._reconnect_task is None
        assert comfoconnect._is_stopping is False
        assert comfoconnect._session_ready is None

    @pytest.mark.asyncio
    async def test_connect_success(self, comfoconnect, mock_connection):
        """Test successful connection with reconnection loop."""
        mock_reader, mock_writer = mock_connection

        async def mock_read_messages():
            try:
                await asyncio.sleep(100)
            except asyncio.CancelledError:
                raise

        with patch("asyncio.open_connection", return_value=(mock_reader, mock_writer)):
            with patch.object(comfoconnect, "cmd_start_session", AsyncMock()):
                with patch.object(comfoconnect, "_read_messages", side_effect=mock_read_messages):
                    await comfoconnect.connect("00000000000000000000000000000001")

        assert comfoconnect.is_connected()
        assert comfoconnect._reconnect_task is not None
        assert not comfoconnect._reconnect_task.done()

        # Clean up
        await comfoconnect.disconnect()

    @pytest.mark.asyncio
    async def test_connect_waits_for_session(self, comfoconnect, mock_connection):
        """Ensure connect does not return until session start completes."""
        mock_reader, mock_writer = mock_connection

        start_called = asyncio.Event()
        allow_start = asyncio.Event()

        async def slow_start_session(*args, **kwargs):
            start_called.set()
            await allow_start.wait()

        async def mock_read_messages():
            try:
                await asyncio.sleep(100)
            except asyncio.CancelledError:
                raise

        with patch("asyncio.open_connection", return_value=(mock_reader, mock_writer)):
            with patch.object(comfoconnect, "cmd_start_session", side_effect=slow_start_session):
                with patch.object(comfoconnect, "_read_messages", side_effect=mock_read_messages):
                    connect_task = asyncio.create_task(comfoconnect.connect(LOCAL_UUID))

                    await start_called.wait()
                    await asyncio.sleep(0)
                    assert not connect_task.done()

                    allow_start.set()
                    await connect_task

        await comfoconnect.disconnect()

    @pytest.mark.asyncio
    async def test_connect_timeout(self, comfoconnect):
        """Test connection timeout on initial connect."""
        async def timeout_coro(*args, **kwargs):
            raise asyncio.TimeoutError()

        with patch("asyncio.open_connection", side_effect=timeout_coro):
            with pytest.raises(AioComfoConnectTimeout, match="Failed to connect within 1 seconds"):
                await comfoconnect.connect(LOCAL_UUID)

        assert comfoconnect._is_stopping

    @pytest.mark.asyncio
    async def test_connect_not_allowed(self, comfoconnect):
        """Test connection when not allowed (not registered)."""
        mock_reader = AsyncMock()
        mock_writer = MagicMock()
        mock_writer.is_closing.return_value = False
        mock_writer.wait_closed = AsyncMock()

        async def raise_not_allowed(*args, **kwargs):
            raise ComfoConnectNotAllowed(Mock(cmd=Mock(reference=1)))

        with patch("asyncio.open_connection", return_value=(mock_reader, mock_writer)):
            with patch.object(comfoconnect, "cmd_start_session", side_effect=raise_not_allowed):
                with patch.object(comfoconnect, "_read_messages", return_value=None):
                    # The connect should try but fail with NotAllowed
                    # Since it's a fatal error, it won't keep retrying
                    with pytest.raises(ComfoConnectNotAllowed):
                        await comfoconnect.connect(LOCAL_UUID)

    @pytest.mark.asyncio
    async def test_reconnect_on_disconnect(self, comfoconnect):
        """Test that reconnection happens after disconnect."""
        mock_reader = AsyncMock()
        mock_writer = MagicMock()
        mock_writer.is_closing.return_value = False
        mock_writer.drain = AsyncMock()
        mock_writer.wait_closed = AsyncMock()

        connection_count = 0

        async def mock_open_connection(*args, **kwargs):
            nonlocal connection_count
            connection_count += 1
            return (mock_reader, mock_writer)

        async def mock_read_messages():
            # Disconnect after first connection
            if connection_count == 1:
                await asyncio.sleep(0.1)
                raise AioComfoConnectNotConnected("Test disconnect")
            # Keep second connection alive
            await asyncio.sleep(100)

        with patch("asyncio.open_connection", side_effect=mock_open_connection):
            with patch.object(comfoconnect, "cmd_start_session", AsyncMock()):
                with patch.object(comfoconnect, "_read_messages", side_effect=mock_read_messages):
                    await comfoconnect.connect(LOCAL_UUID)

                    # Wait for reconnection
                    await asyncio.sleep(1.5)

        # Should have connected twice
        assert connection_count >= 2

        # Clean up
        await comfoconnect.disconnect()

    @pytest.mark.asyncio
    async def test_disconnect(self, comfoconnect):
        """Test disconnection."""
        mock_reader = AsyncMock()
        mock_writer = MagicMock()
        mock_writer.is_closing.return_value = False
        mock_writer.drain = AsyncMock()
        mock_writer.wait_closed = AsyncMock()

        with patch("asyncio.open_connection", return_value=(mock_reader, mock_writer)):
            with patch.object(comfoconnect, "cmd_start_session", AsyncMock()):
                with patch.object(comfoconnect, "cmd_rpdo_request", AsyncMock()):
                    async def mock_read():
                        await asyncio.sleep(100)

                    with patch.object(comfoconnect, "_read_messages", side_effect=mock_read):
                        await comfoconnect.connect(LOCAL_UUID)

        assert comfoconnect.is_connected()

        await comfoconnect.disconnect()

        assert comfoconnect._is_stopping
        assert not comfoconnect.is_connected()
        assert comfoconnect._reconnect_task is None

    @pytest.mark.asyncio
    async def test_disconnect_when_not_connected(self, comfoconnect):
        """Test disconnecting when not connected."""
        await comfoconnect.disconnect()
        assert comfoconnect._is_stopping

    @pytest.mark.asyncio
    async def test_register_sensor(self, comfoconnect):
        """Test registering a sensor."""
        mock_reader = AsyncMock()
        mock_writer = MagicMock()
        mock_writer.is_closing.return_value = False
        mock_writer.drain = AsyncMock()
        mock_writer.wait_closed = AsyncMock()

        with patch("asyncio.open_connection", return_value=(mock_reader, mock_writer)):
            with patch.object(comfoconnect, "cmd_start_session", AsyncMock()):
                with patch.object(comfoconnect, "cmd_rpdo_request", AsyncMock()) as mock_rpdo:
                    async def mock_read():
                        await asyncio.sleep(100)

                    with patch.object(comfoconnect, "_read_messages", side_effect=mock_read):
                        await comfoconnect.connect(LOCAL_UUID)

                    sensor = create_sensor(name="test_sensor", sensor_id=276, sensor_type=1)
                    await comfoconnect.register_sensor(sensor)

                    assert 276 in comfoconnect._sensors
                    assert comfoconnect._sensors[276] == sensor
                    assert 276 in comfoconnect._sensors_values
                    mock_rpdo.assert_called_with(276, 1)

                    # Clean up
                    await comfoconnect.disconnect()

    @pytest.mark.asyncio
    async def test_deregister_sensor(self, comfoconnect):
        """Test deregistering a sensor."""
        mock_reader = AsyncMock()
        mock_writer = MagicMock()
        mock_writer.is_closing.return_value = False
        mock_writer.drain = AsyncMock()
        mock_writer.wait_closed = AsyncMock()

        with patch("asyncio.open_connection", return_value=(mock_reader, mock_writer)):
            with patch.object(comfoconnect, "cmd_start_session", AsyncMock()):
                with patch.object(comfoconnect, "cmd_rpdo_request", AsyncMock()) as mock_rpdo:
                    async def mock_read():
                        await asyncio.sleep(100)

                    with patch.object(comfoconnect, "_read_messages", side_effect=mock_read):
                        await comfoconnect.connect(LOCAL_UUID)

                    sensor = create_sensor(name="test_sensor", sensor_id=276, sensor_type=1)
                    await comfoconnect.register_sensor(sensor)
                    await comfoconnect.deregister_sensor(sensor)

                    assert 276 not in comfoconnect._sensors
                    assert 276 not in comfoconnect._sensors_values
                    assert mock_rpdo.call_args_list[-1] == call(276, 1, timeout=0)

                    # Clean up
                    await comfoconnect.disconnect()

    @pytest.mark.asyncio
    async def test_sensor_callback(self, comfoconnect):
        """Test sensor callback is called."""
        mock_callback = Mock()
        comfoconnect._sensor_callback_fn = mock_callback

        sensor = create_sensor(name="test_sensor", sensor_id=276, sensor_type=1)
        comfoconnect._sensors[276] = sensor

        # Call the internal sensor callback
        comfoconnect._sensor_callback(276, 100)

        mock_callback.assert_called_once()
        args = mock_callback.call_args[0]
        assert args[0] == sensor
        assert args[1] == 100

    @pytest.mark.asyncio
    async def test_sensor_callback_with_value_fn(self, comfoconnect):
        """Test sensor callback with value transformation function."""
        mock_callback = Mock()
        comfoconnect._sensor_callback_fn = mock_callback

        # Sensor with value transformation function
        sensor = create_sensor(name="test_sensor", sensor_id=276, sensor_type=1, value_fn=lambda x: x / 10)
        comfoconnect._sensors[276] = sensor

        comfoconnect._sensor_callback(276, 1000)

        mock_callback.assert_called_once()
        args = mock_callback.call_args[0]
        assert args[0] == sensor
        assert args[1] == 100  # 1000 / 10

    @pytest.mark.asyncio
    async def test_sensor_hold(self, comfoconnect):
        """Test sensor hold mechanism."""
        mock_callback = Mock()
        comfoconnect._sensor_callback_fn = mock_callback
        comfoconnect.sensor_delay = 2

        sensor = create_sensor(name="test_sensor", sensor_id=276, sensor_type=1)
        comfoconnect._sensors[276] = sensor

        mock_reader = AsyncMock()
        mock_writer = MagicMock()
        mock_writer.is_closing.return_value = False
        mock_writer.drain = AsyncMock()
        mock_writer.wait_closed = AsyncMock()

        with patch("asyncio.open_connection", return_value=(mock_reader, mock_writer)):
            with patch.object(comfoconnect, "cmd_start_session", AsyncMock()):
                with patch.object(comfoconnect, "_send", AsyncMock()):
                    async def mock_read():
                        await asyncio.sleep(100)

                    with patch.object(comfoconnect, "_read_messages", side_effect=mock_read):
                        await comfoconnect.connect(LOCAL_UUID)

        # Sensor hold should be active
        assert comfoconnect._sensor_hold is not None

        # Sensor callback should not emit yet
        comfoconnect._sensor_callback(276, 100)
        assert not mock_callback.called

        # Wait for sensor hold to expire
        await asyncio.sleep(2.5)

        # Now callback should be called with cached value
        assert mock_callback.called

        # Clean up
        await comfoconnect.disconnect()

    @pytest.mark.asyncio
    async def test_alarm_callback(self, comfoconnect):
        """Test alarm callback is called."""
        mock_callback = Mock()
        comfoconnect._alarm_callback_fn = mock_callback

        mock_alarm = Mock()
        mock_alarm.swProgramVersion = 3222278145  # Firmware > 1.4.0
        # Set bit 52 which corresponds to "The supply air fan has a malfunction"
        # Byte index 6, bit 4 (52 = 6*8 + 4)
        mock_alarm.errors = b"\x00\x00\x00\x00\x00\x00\x10\x00"

        comfoconnect._alarm_callback(1, mock_alarm)

        mock_callback.assert_called_once()
        args = mock_callback.call_args[0]
        assert args[0] == 1  # node_id
        assert isinstance(args[1], dict)  # errors dict
        assert 52 in args[1]  # Should contain error bit 52

    @pytest.mark.asyncio
    async def test_sensors_reregistered_after_reconnect(self, comfoconnect):
        """Test that sensors are re-registered after reconnection."""
        mock_reader = AsyncMock()
        mock_writer = MagicMock()
        mock_writer.is_closing.return_value = False
        mock_writer.drain = AsyncMock()
        mock_writer.wait_closed = AsyncMock()

        connection_count = 0
        rpdo_calls = []

        async def mock_rpdo(*args, **kwargs):
            rpdo_calls.append(args)

        async def mock_open_connection(*args, **kwargs):
            nonlocal connection_count
            connection_count += 1
            return (mock_reader, mock_writer)

        async def mock_read_messages():
            # Disconnect after first connection
            if connection_count == 1:
                await asyncio.sleep(0.1)
                raise AioComfoConnectNotConnected("Test disconnect")
            # Keep second connection alive
            await asyncio.sleep(100)

        # Register sensors before connecting
        sensor1 = create_sensor(name="test_sensor1", sensor_id=276, sensor_type=1)
        sensor2 = create_sensor(name="test_sensor2", sensor_id=277, sensor_type=1)
        comfoconnect._sensors[276] = sensor1
        comfoconnect._sensors[277] = sensor2

        with patch("asyncio.open_connection", side_effect=mock_open_connection):
            with patch.object(comfoconnect, "cmd_start_session", AsyncMock()):
                with patch.object(comfoconnect, "cmd_rpdo_request", side_effect=mock_rpdo):
                    with patch.object(comfoconnect, "_read_messages", side_effect=mock_read_messages):
                        await comfoconnect.connect(LOCAL_UUID)

                        # Wait for reconnection
                        await asyncio.sleep(1.5)

        # Sensors should be registered twice (once per connection)
        assert len([c for c in rpdo_calls if c[0] == 276]) >= 2
        assert len([c for c in rpdo_calls if c[0] == 277]) >= 2

        # Clean up
        await comfoconnect.disconnect()

    @pytest.mark.asyncio
    async def test_connect_already_connecting(self, comfoconnect):
        """Test connecting when already connecting."""
        mock_reader = AsyncMock()
        mock_writer = MagicMock()
        mock_writer.is_closing.return_value = False
        mock_writer.drain = AsyncMock()
        mock_writer.wait_closed = AsyncMock()

        with patch("asyncio.open_connection", return_value=(mock_reader, mock_writer)):
            with patch.object(comfoconnect, "cmd_start_session", AsyncMock()):
                async def mock_read():
                    await asyncio.sleep(100)

                with patch.object(comfoconnect, "_read_messages", side_effect=mock_read):
                    await comfoconnect.connect(LOCAL_UUID)

        # Try to connect again - should do nothing
        await comfoconnect.connect(LOCAL_UUID)

        # Clean up
        await comfoconnect.disconnect()

    @pytest.mark.asyncio
    async def test_reconnect_delay_on_timeout(self, comfoconnect):
        """Test that reconnection waits 5 seconds after timeout."""
        connection_attempts = []

        async def mock_open_connection(*args, **kwargs):
            connection_attempts.append(asyncio.get_event_loop().time())
            raise asyncio.TimeoutError()

        with patch("asyncio.open_connection", side_effect=mock_open_connection):
            try:
                await comfoconnect.connect(LOCAL_UUID)
            except AioComfoConnectTimeout:
                pass

        # Should have stopped trying to connect
        assert comfoconnect._is_stopping

    @pytest.mark.asyncio
    async def test_get_mode(self, comfoconnect):
        """Test getting ventilation mode."""
        mock_response = Mock()
        mock_response.message = bytes([0x00])  # Auto mode

        with patch.object(comfoconnect, "cmd_rmi_request", AsyncMock(return_value=mock_response)):
            from aiocomfoconnect.const import VentilationMode

            mode = await comfoconnect.get_mode()
            assert mode == VentilationMode.AUTO

    @pytest.mark.asyncio
    async def test_set_speed(self, comfoconnect):
        """Test setting ventilation speed."""
        with patch.object(comfoconnect, "cmd_rmi_request", AsyncMock()) as mock_rmi:
            from aiocomfoconnect.const import VentilationSpeed

            await comfoconnect.set_speed(VentilationSpeed.LOW)
            mock_rmi.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_property(self, comfoconnect):
        """Test getting a property."""
        from aiocomfoconnect.const import PdoType
        from aiocomfoconnect.properties import Property

        mock_response = Mock()
        mock_response.message = b"\x64\x00"  # 100 in little-endian

        with patch.object(comfoconnect, "cmd_rmi_request", AsyncMock(return_value=mock_response)):
            prop = Property(unit=1, subunit=1, property_id=8, property_type=PdoType.TYPE_CN_INT16)
            value = await comfoconnect.get_property(prop)
            assert value == 100

    @pytest.mark.asyncio
    async def test_clear_errors(self, comfoconnect):
        """Test clearing errors."""
        with patch.object(comfoconnect, "cmd_rmi_request", AsyncMock()) as mock_rmi:
            await comfoconnect.clear_errors()
            mock_rmi.assert_called_once()
