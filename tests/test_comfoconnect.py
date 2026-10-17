"""Tests for the ComfoConnect class."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, Mock, call, patch

import pytest

from aiocomfoconnect.comfoconnect import ComfoConnect
from aiocomfoconnect.const import ERRORS, ERRORS_BASE, ProductId
from aiocomfoconnect.exceptions import (
    AioComfoConnectNotConnected,
    AioComfoConnectTimeout,
    ComfoClimeNotFoundException,
    ComfoConnectBadRequest,
    ComfoConnectNotAllowed,
    VentilationUnitNotFoundException,
)
from aiocomfoconnect.properties import PROPERTY_CLIME_HEATPUMP_STANDBY, PROPERTY_CLIME_HEATING_COMFORT_TEMP
from aiocomfoconnect.protobuf import zehnder_pb2
from tests.conftest import create_sensor, node_notification

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
    async def test_connect_discovers_ventilation_node(self, comfoconnect, mock_connection):
        """Test that connect waits for the ventilation unit before it reports the session as ready."""
        mock_reader, mock_writer = mock_connection

        async def mock_read_messages():
            await asyncio.sleep(100)

        async def announce_nodes():
            """Announce the nodes like a ComfoAir Flex setup does, in reply to the node request."""
            node_notification(comfoconnect, node_id=41, product_id=ProductId.COMFOAIRFLEXCONNECTIONBOARD)
            node_notification(comfoconnect, node_id=45, product_id=ProductId.COMFOAIRFLEX)

        with patch("asyncio.open_connection", return_value=(mock_reader, mock_writer)):
            with patch.object(comfoconnect, "cmd_start_session", AsyncMock()):
                with patch.object(comfoconnect, "cmd_node_request", side_effect=announce_nodes):
                    with patch.object(comfoconnect, "_read_messages", side_effect=mock_read_messages):
                        await comfoconnect.connect(LOCAL_UUID)

        assert comfoconnect.ventilation_node_id == 45

        # Properties should be read from the discovered node, not from node 1.
        with patch.object(comfoconnect, "_send", MagicMock()) as mock_send:
            comfoconnect.cmd_rmi_request(b"\x01\x01\x01\x10\x08")
        assert mock_send.call_args[0][2]["nodeId"] == 45

        await comfoconnect.disconnect()

    @pytest.mark.asyncio
    async def test_connect_without_node_notifications(self, comfoconnect, mock_connection):
        """Test that we don't consider the session ready when no ventilation unit is announced."""
        mock_reader, mock_writer = mock_connection

        async def mock_read_messages():
            await asyncio.sleep(100)

        with patch("asyncio.open_connection", return_value=(mock_reader, mock_writer)):
            with patch.object(comfoconnect, "cmd_start_session", AsyncMock()):
                with patch.object(comfoconnect, "cmd_node_request", AsyncMock()):
                    with patch.object(comfoconnect, "_read_messages", side_effect=mock_read_messages):
                        # The reconnect loop keeps retrying, so connect() gives up after its timeout.
                        with pytest.raises(AioComfoConnectTimeout):
                            await comfoconnect.connect(LOCAL_UUID)

        assert comfoconnect.ventilation_node_id is None

    @pytest.mark.asyncio
    async def test_rmi_request_without_ventilation_node(self, comfoconnect):
        """Test that RMI commands are refused instead of being sent to node 1."""
        with patch.object(comfoconnect, "is_connected", return_value=True):
            with pytest.raises(VentilationUnitNotFoundException):
                await comfoconnect.get_speed()

    @pytest.mark.asyncio
    async def test_rmi_request_after_disconnect(self, comfoconnect, mock_connection):
        """Test that commands raise AioComfoConnectNotConnected after a disconnect, not VentilationUnitNotFoundException."""
        mock_reader, mock_writer = mock_connection

        async def mock_read_messages():
            await asyncio.sleep(100)

        with patch("asyncio.open_connection", return_value=(mock_reader, mock_writer)):
            with patch.object(comfoconnect, "cmd_start_session", AsyncMock()):
                with patch.object(comfoconnect, "_read_messages", side_effect=mock_read_messages):
                    await comfoconnect.connect(LOCAL_UUID)

        assert comfoconnect.ventilation_node_id == 1

        await comfoconnect.disconnect()

        with pytest.raises(AioComfoConnectNotConnected):
            await comfoconnect.get_speed()

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
    async def test_deregister_unregistered_sensor(self, comfoconnect):
        """Test that deregistering a sensor that was never registered doesn't raise."""
        with patch.object(comfoconnect, "cmd_rpdo_request", AsyncMock()) as mock_rpdo:
            await comfoconnect.deregister_sensor(create_sensor(name="test_sensor", sensor_id=276, sensor_type=1))

            mock_rpdo.assert_called_once_with(276, 1, timeout=0)

    @pytest.mark.asyncio
    async def test_deregister_sensor_when_disconnected(self, comfoconnect):
        """Test that a sensor is forgotten locally, even when the bridge can't be told."""
        sensor = create_sensor(name="test_sensor", sensor_id=276, sensor_type=1)
        comfoconnect._sensors[sensor.id] = sensor
        comfoconnect._sensors_values[sensor.id] = None

        with pytest.raises(AioComfoConnectNotConnected):
            await comfoconnect.deregister_sensor(sensor)

        # It must not be subscribed again on the next reconnect.
        assert 276 not in comfoconnect._sensors
        assert 276 not in comfoconnect._sensors_values

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
        assert 276 in comfoconnect._sensor_holds

        # Sensor callback should not emit the invalid value yet
        comfoconnect._sensor_callback(276, 0)
        assert not mock_callback.called

        # Wait for sensor hold to expire
        await asyncio.sleep(2.5)

        # Now callback should be called with cached value
        mock_callback.assert_called_once_with(sensor, 0)

        # Clean up
        await comfoconnect.disconnect()

    @pytest.mark.asyncio
    async def test_sensor_hold_released_on_valid_value(self, comfoconnect):
        """Test that a sensor hold is released as soon as a non-zero value arrives."""
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

        # The invalid value that the bridge sends when we subscribe is held back.
        comfoconnect._sensor_callback(276, 0)
        assert not mock_callback.called

        # A non-zero value is valid, so it is emitted right away and the hold is released.
        comfoconnect._sensor_callback(276, 69)
        mock_callback.assert_called_once_with(sensor, 69)
        assert 276 not in comfoconnect._sensor_holds

        # Zero values are emitted normally once the hold is released.
        comfoconnect._sensor_callback(276, 0)
        mock_callback.assert_called_with(sensor, 0)

        # The expired hold doesn't emit the cached value again.
        await asyncio.sleep(2.5)
        assert mock_callback.call_count == 2

        # Clean up
        await comfoconnect.disconnect()

    @pytest.mark.asyncio
    async def test_sensor_hold_when_registered_after_connect(self, comfoconnect):
        """Test that a sensor registered after the connect hold expired is held as well."""
        mock_callback = Mock()
        comfoconnect._sensor_callback_fn = mock_callback
        comfoconnect.sensor_delay = 1

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

                    # The hold that was started when we connected has expired by now.
                    await asyncio.sleep(1.5)

                    sensor = create_sensor(name="test_sensor", sensor_id=276, sensor_type=1)
                    await comfoconnect.register_sensor(sensor)

                    # The invalid value that the bridge sends when we subscribe should not be emitted.
                    comfoconnect._sensor_callback(276, 0)
                    assert not mock_callback.called

                    # The correct value arrives during the hold and is emitted right away.
                    comfoconnect._sensor_callback(276, 69)
                    mock_callback.assert_called_once_with(sensor, 69)

                    # Clean up
                    await comfoconnect.disconnect()

    @pytest.mark.asyncio
    async def test_alarm_callback(self, comfoconnect):
        """Test alarm callback is called."""
        mock_callback = Mock()
        comfoconnect._alarm_callback_fn = mock_callback

        node_notification(comfoconnect, node_id=1, product_id=ProductId.COMFOAIRQ)

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
        assert args[1] == {52: ERRORS[52]}

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "sw_version, bit",
        [
            (3222278145, 36),  # A gap in ERRORS
            (3222278145, 105),  # Beyond ERRORS
            (3222278144, 87),  # Beyond ERRORS_140
        ],
    )
    async def test_alarm_callback_unknown_bit(self, comfoconnect, sw_version, bit):
        """Test that an alarm bit we have no message for is reported as unknown instead of raising."""
        mock_callback = Mock()
        comfoconnect._alarm_callback_fn = mock_callback
        node_notification(comfoconnect, node_id=1, product_id=ProductId.COMFOAIRQ)

        alarm = zehnder_pb2.CnAlarmNotification()
        alarm.nodeId = 1
        alarm.swProgramVersion = sw_version
        errors = bytearray(14)
        errors[bit // 8] |= 1 << (bit % 8)
        errors[52 // 8] |= 1 << (52 % 8)
        alarm.errors = bytes(errors)

        comfoconnect._alarm_callback(1, alarm)

        mock_callback.assert_called_once_with(1, {52: ERRORS_BASE[52], bit: f"Unknown error {bit}"})

    @pytest.mark.asyncio
    async def test_alarm_callback_other_node(self, comfoconnect):
        """Test that alarms of a node that isn't the ventilation unit aren't decoded with its error table."""
        mock_callback = Mock()
        comfoconnect._alarm_callback_fn = mock_callback
        node_notification(comfoconnect, node_id=1, product_id=ProductId.COMFOAIRQ)
        node_notification(comfoconnect, node_id=10, product_id=ProductId.COMFOSENSE)

        alarm = zehnder_pb2.CnAlarmNotification()
        alarm.nodeId = 10
        alarm.swProgramVersion = 3222278145
        alarm.errors = b"\x00\x00\x20"  # Bit 21

        comfoconnect._alarm_callback(10, alarm)

        mock_callback.assert_called_once_with(10, {21: "Unknown error 21"})

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
    async def test_failing_sensor_does_not_block_session(self, comfoconnect, mock_connection):
        """Test that a sensor the bridge rejects on reconnect doesn't stop the others or the session."""
        mock_reader, mock_writer = mock_connection
        rpdo_calls = []

        async def mock_rpdo(pdid, pdo_type, *args, **kwargs):
            rpdo_calls.append(pdid)
            if pdid == 276:
                raise ComfoConnectBadRequest("rejected")

        async def mock_read():
            await asyncio.sleep(100)

        sensor1 = create_sensor(name="test_sensor1", sensor_id=276, sensor_type=1)
        sensor2 = create_sensor(name="test_sensor2", sensor_id=277, sensor_type=1)
        comfoconnect._sensors[276] = sensor1
        comfoconnect._sensors[277] = sensor2

        with patch("asyncio.open_connection", return_value=(mock_reader, mock_writer)):
            with patch.object(comfoconnect, "cmd_start_session", AsyncMock()):
                with patch.object(comfoconnect, "cmd_rpdo_request", side_effect=mock_rpdo):
                    with patch.object(comfoconnect, "_read_messages", side_effect=mock_read):
                        await comfoconnect.connect(LOCAL_UUID)

                        assert rpdo_calls == [276, 277]
                        assert comfoconnect.is_connected()

                        # Clean up
                        await comfoconnect.disconnect()

    @pytest.mark.asyncio
    async def test_register_sensor_while_resubscribing(self, comfoconnect, mock_connection):
        """Test that registering a sensor while the sensors are re-subscribed doesn't break the session."""
        mock_reader, mock_writer = mock_connection
        sensor1 = create_sensor(name="test_sensor1", sensor_id=276, sensor_type=1)
        sensor2 = create_sensor(name="test_sensor2", sensor_id=277, sensor_type=1)
        comfoconnect._sensors[276] = sensor1

        async def mock_rpdo(pdid, pdo_type, *args, **kwargs):
            if pdid == 276:
                # Another task registers a sensor while we wait for the bridge.
                comfoconnect._sensors[277] = sensor2

        async def mock_read():
            await asyncio.sleep(100)

        with patch("asyncio.open_connection", return_value=(mock_reader, mock_writer)):
            with patch.object(comfoconnect, "cmd_start_session", AsyncMock()):
                with patch.object(comfoconnect, "cmd_rpdo_request", side_effect=mock_rpdo):
                    with patch.object(comfoconnect, "_read_messages", side_effect=mock_read):
                        await comfoconnect.connect(LOCAL_UUID)

                        assert comfoconnect.is_connected()

                        # Clean up
                        await comfoconnect.disconnect()

    @pytest.mark.asyncio
    async def test_register_sensor_failure_rolls_back(self, comfoconnect, mock_connection):
        """Test that a sensor is not kept when the bridge rejects the subscription."""
        mock_reader, mock_writer = mock_connection

        async def mock_read():
            await asyncio.sleep(100)

        with patch("asyncio.open_connection", return_value=(mock_reader, mock_writer)):
            with patch.object(comfoconnect, "cmd_start_session", AsyncMock()):
                with patch.object(comfoconnect, "cmd_rpdo_request", AsyncMock()) as mock_rpdo:
                    with patch.object(comfoconnect, "_read_messages", side_effect=mock_read):
                        await comfoconnect.connect(LOCAL_UUID)

                    comfoconnect.sensor_delay = 5
                    mock_rpdo.side_effect = ComfoConnectBadRequest("rejected")

                    sensor = create_sensor(name="test_sensor", sensor_id=276, sensor_type=1)
                    with pytest.raises(ComfoConnectBadRequest):
                        await comfoconnect.register_sensor(sensor)

                    assert 276 not in comfoconnect._sensors
                    assert 276 not in comfoconnect._sensors_values
                    assert 276 not in comfoconnect._sensor_holds

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
    async def test_flow_for_speed_rejects_invalid_speed(self, comfoconnect):
        """Test that an invalid speed raises a ValueError instead of an UnboundLocalError."""
        with patch.object(comfoconnect, "cmd_rmi_request", AsyncMock()) as mock_rmi:
            with pytest.raises(ValueError):
                await comfoconnect.get_flow_for_speed("turbo")
            with pytest.raises(ValueError):
                await comfoconnect.set_flow_for_speed("turbo", 100)

            mock_rmi.assert_not_called()

    @pytest.mark.asyncio
    async def test_set_comfocool_mode_rejects_invalid_mode(self, comfoconnect):
        """Test that an invalid comfocool mode raises like the other setters."""
        with patch.object(comfoconnect, "cmd_rmi_request", AsyncMock()) as mock_rmi:
            with pytest.raises(ValueError):
                await comfoconnect.set_comfocool_mode("on")

            mock_rmi.assert_not_called()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("first_byte,expected", [(0x00, "auto"), (0x01, "off")])
    async def test_get_comfocool_mode(self, comfoconnect, first_byte, expected):
        """Test that the comfocool getter returns the same values the setter takes."""
        mock_response = Mock()
        mock_response.message = bytes([first_byte, 0x00, 0x00, 0x00, 0x00, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0x00])

        with patch.object(comfoconnect, "cmd_rmi_request", AsyncMock(return_value=mock_response)):
            assert await comfoconnect.get_comfocool_mode() == expected

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "mode,expected_commands",
        [
            ("auto", [b"\x85\x15\x08\x01", b"\x85\x15\x01\x01"]),
            ("manual", [b"\x84\x15\x08\x01\x00\x00\x00\x00\x01\x00\x00\x00\x01"]),
        ],
    )
    async def test_set_mode_restores_schedule_only_for_auto(self, comfoconnect, mode, expected_commands):
        """Auto cancels the speed timer; manual retains the selected speed."""
        with patch.object(comfoconnect, "cmd_rmi_request", AsyncMock()) as mock_rmi:
            await comfoconnect.set_mode(mode)
            assert mock_rmi.await_args_list == [call(command) for command in expected_commands]

    @pytest.mark.asyncio
    async def test_auto_mode_reports_a_failed_speed_override_cancellation(self, comfoconnect):
        """A partially completed mode change must not report full success."""
        with patch.object(comfoconnect, "cmd_rmi_request", AsyncMock(side_effect=[Mock(), AioComfoConnectNotConnected("Disconnected")])):
            with pytest.raises(AioComfoConnectNotConnected):
                await comfoconnect.set_mode("auto")

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
    async def test_get_property_constraints(self, comfoconnect):
        """Test getting a property with its range and step size in one request."""
        from aiocomfoconnect.properties import PROPERTY_RMOT_COOLING_THRESHOLD, PropertyConstraints

        mock_response = Mock()
        # Captured from a ComfoAir Q: 16.0 °C, range 15.0 - 40.0 °C, step 1.0 °C.
        mock_response.message = bytes.fromhex("a000960090010a00")

        with patch.object(comfoconnect, "cmd_rmi_request", AsyncMock(return_value=mock_response)) as mock_rmi:
            constraints = await comfoconnect.get_property_constraints(PROPERTY_RMOT_COOLING_THRESHOLD)

            assert constraints == PropertyConstraints(value=160, minimum=150, maximum=400, step=10)
            mock_rmi.assert_called_once_with(bytes([0x01, 0x1D, 0x01, 0x70, 0x03]), node_id=None)

    @pytest.mark.asyncio
    async def test_get_property_constraints_uint8(self, comfoconnect):
        """Test that the value size follows the property type."""
        from aiocomfoconnect.properties import PROPERTY_TEMPERATURE_PROFILE_MODE, PropertyConstraints

        mock_response = Mock()
        mock_response.message = bytes.fromhex("00000101")  # adaptive, range 0 - 1, step 1

        with patch.object(comfoconnect, "cmd_rmi_request", AsyncMock(return_value=mock_response)):
            constraints = await comfoconnect.get_property_constraints(PROPERTY_TEMPERATURE_PROFILE_MODE)

            assert constraints == PropertyConstraints(value=0, minimum=0, maximum=1, step=1)

    @pytest.mark.asyncio
    async def test_get_property_constraints_sensor_ventilation(self, comfoconnect):
        """Test that the sensor ventilation properties are single bytes, like the unit sends them."""
        from aiocomfoconnect.properties import (
            PROPERTY_SENSOR_VENTILATION_HUMIDITY_COMFORT,
            PROPERTY_SENSOR_VENTILATION_HUMIDITY_PROTECTION,
            PROPERTY_SENSOR_VENTILATION_TEMP_PASSIVE,
            PropertyConstraints,
        )

        mock_response = Mock()
        mock_response.message = bytes.fromhex("01000201")  # autoonly, range 0 - 2, step 1

        with patch.object(comfoconnect, "cmd_rmi_request", AsyncMock(return_value=mock_response)):
            for prop in (PROPERTY_SENSOR_VENTILATION_TEMP_PASSIVE, PROPERTY_SENSOR_VENTILATION_HUMIDITY_COMFORT, PROPERTY_SENSOR_VENTILATION_HUMIDITY_PROTECTION):
                assert await comfoconnect.get_property_constraints(prop) == PropertyConstraints(value=1, minimum=0, maximum=2, step=1)

    @pytest.mark.asyncio
    async def test_get_property_constraints_signed(self, comfoconnect):
        """Test that signed property types keep negative values."""
        from aiocomfoconnect.const import PdoType
        from aiocomfoconnect.properties import Property

        mock_response = Mock()
        mock_response.message = bytes.fromhex("ceff9cff64000100")  # -5.0, range -10.0 - 10.0, step 0.1

        with patch.object(comfoconnect, "cmd_rmi_request", AsyncMock(return_value=mock_response)):
            constraints = await comfoconnect.get_property_constraints(Property(0x1D, 0x01, 0x02, PdoType.TYPE_CN_INT16))

            assert (constraints.value, constraints.minimum, constraints.maximum, constraints.step) == (-50, -100, 100, 1)

    @pytest.mark.asyncio
    async def test_get_property_constraints_rejects_invalid(self, comfoconnect):
        """Test that non-numeric types and unexpected responses raise."""
        from aiocomfoconnect.properties import PROPERTY_NAME, PROPERTY_RMOT_COOLING_THRESHOLD

        with pytest.raises(ValueError):
            await comfoconnect.get_property_constraints(PROPERTY_NAME)

        mock_response = Mock()
        mock_response.message = bytes.fromhex("a000")  # only the value

        with patch.object(comfoconnect, "cmd_rmi_request", AsyncMock(return_value=mock_response)), pytest.raises(ValueError):
            await comfoconnect.get_property_constraints(PROPERTY_RMOT_COOLING_THRESHOLD)

    @pytest.mark.asyncio
    async def test_clear_errors(self, comfoconnect):
        """Test clearing errors."""
        with patch.object(comfoconnect, "cmd_rmi_request", AsyncMock()) as mock_rmi:
            await comfoconnect.clear_errors()
            mock_rmi.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_comfoclime_property(self, comfoconnect):
        """Test that a ComfoClime property is read from the ComfoClime node."""
        node_notification(comfoconnect, node_id=1, product_id=ProductId.COMFOAIRQ)
        node_notification(comfoconnect, node_id=2, product_id=ProductId.COMFOCLIME)

        mock_response = Mock()
        mock_response.message = b"\xd7\x00"  # 215 in little-endian

        with patch.object(comfoconnect, "cmd_rmi_request", AsyncMock(return_value=mock_response)) as mock_rmi:
            value = await comfoconnect.get_comfoclime_property(PROPERTY_CLIME_HEATING_COMFORT_TEMP)

            assert value == 215
            mock_rmi.assert_called_once_with(bytes([0x01, 0x16, 0x01, 0x10, 0x09]), node_id=2)

    @pytest.mark.asyncio
    async def test_set_comfoclime_property(self, comfoconnect):
        """Test that a ComfoClime property is written to the ComfoClime node."""
        node_notification(comfoconnect, node_id=2, product_id=ProductId.COMFOCLIME)

        with patch.object(comfoconnect, "cmd_rmi_request", AsyncMock()) as mock_rmi:
            await comfoconnect.set_comfoclime_property(PROPERTY_CLIME_HEATING_COMFORT_TEMP, 215)

            mock_rmi.assert_called_once_with(bytes([0x03, 0x16, 0x01, 0x09, 0xD7, 0x00]), node_id=2)

    @pytest.mark.asyncio
    async def test_comfoclime_property_without_comfoclime(self, comfoconnect):
        """Test that addressing a ComfoClime that isn't on the bus raises."""
        node_notification(comfoconnect, node_id=1, product_id=ProductId.COMFOAIRQ)

        with pytest.raises(ComfoClimeNotFoundException):
            await comfoconnect.get_comfoclime_property(PROPERTY_CLIME_HEATING_COMFORT_TEMP)

    @pytest.mark.asyncio
    async def test_set_comfoclime_standby_property(self, comfoconnect):
        """Test the verified ComfoClime standby property framing."""
        node_notification(comfoconnect, node_id=11, product_id=ProductId.COMFOCLIME)

        with patch.object(comfoconnect, "cmd_rmi_request", AsyncMock()) as mock_rmi:
            await comfoconnect.set_comfoclime_property(PROPERTY_CLIME_HEATPUMP_STANDBY, 1)

            mock_rmi.assert_called_once_with(bytes([0x03, 0x16, 0x01, 0x15, 0x01]), node_id=11)
