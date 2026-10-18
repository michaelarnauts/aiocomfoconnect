"""Tests for the Bridge class."""

import asyncio
import gc
import socket
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from aiocomfoconnect.bridge import GATEWAY_TYPE_PRO, Bridge, EventBus, Message, Node
from aiocomfoconnect.comfoconnect import ComfoConnect
from aiocomfoconnect.const import GatewayType, ProductId
from aiocomfoconnect.protobuf import zehnder_pb2
from tests.conftest import create_sensor, node_notification

LOCAL_UUID = "00000000000000000000000000000001"

from aiocomfoconnect.exceptions import (
    AioComfoConnectNotConnected,
    AioComfoConnectNotReachable,
    AioComfoConnectTimeout,
    ComfoConnectNotAllowed,
    VentilationUnitNotFoundException,
)


class TestEventBus:
    """Test the EventBus class."""

    @pytest.mark.asyncio
    async def test_add_listener(self):
        """Test adding a listener."""
        bus = EventBus()
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        bus.add_listener("test_event", future)

        assert "test_event" in bus.listeners
        assert future in bus.listeners["test_event"]

    @pytest.mark.asyncio
    async def test_add_multiple_listeners(self):
        """Test adding multiple listeners to the same event."""
        bus = EventBus()
        loop = asyncio.get_running_loop()
        future1 = loop.create_future()
        future2 = loop.create_future()

        bus.add_listener("test_event", future1)
        bus.add_listener("test_event", future2)

        assert len(bus.listeners["test_event"]) == 2
        assert future1 in bus.listeners["test_event"]
        assert future2 in bus.listeners["test_event"]

    @pytest.mark.asyncio
    async def test_emit_result(self):
        """Test emitting a result to listeners."""
        bus = EventBus()
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        bus.add_listener("test_event", future)

        bus.emit("test_event", "test_result")

        assert future.done()
        assert future.result() == "test_result"
        assert "test_event" not in bus.listeners

    @pytest.mark.asyncio
    async def test_emit_exception(self):
        """Test emitting an exception to listeners."""
        bus = EventBus()
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        bus.add_listener("test_event", future)

        test_exception = ValueError("test error")
        bus.emit("test_event", test_exception)

        assert future.done()
        with pytest.raises(ValueError, match="test error"):
            future.result()
        assert "test_event" not in bus.listeners

    @pytest.mark.asyncio
    async def test_fail_all(self):
        """Test failing all pending listeners."""
        bus = EventBus()
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        bus.add_listener("test_event", future)

        bus.fail_all(RuntimeError("boom"))

        assert future.done()
        with pytest.raises(RuntimeError, match="boom"):
            future.result()
        assert bus.listeners == {}


class TestBridge:
    """Test the Bridge class."""

    @pytest.fixture
    def bridge(self):
        """Create a Bridge instance for testing."""
        return Bridge("192.168.1.100", "00000000000000000000000000000001")

    @pytest.mark.asyncio
    async def test_init(self, bridge):
        """Test Bridge initialization."""
        assert bridge.host == "192.168.1.100"
        assert bridge.uuid == "00000000000000000000000000000001"
        assert bridge._reader is None
        assert bridge._writer is None
        assert bridge._reference is None
        assert bridge._event_bus is None
        assert not bridge.is_connected()

    @pytest.mark.asyncio
    async def test_connect_success(self, bridge, mock_connection):
        """Test successful connection."""
        mock_reader, mock_writer = mock_connection

        with patch("asyncio.open_connection", return_value=(mock_reader, mock_writer)):
            # Mock the _read_messages task to block indefinitely
            async def mock_read_messages():
                try:
                    await asyncio.sleep(100)
                except asyncio.CancelledError:
                    raise

            with patch.object(bridge, "_read_messages", side_effect=mock_read_messages):
                await bridge.connect(LOCAL_UUID)

        assert bridge.is_connected()
        assert bridge._local_uuid == LOCAL_UUID
        assert bridge._reference is not None
        assert bridge._event_bus is not None
        assert bridge._read_task is not None

        # Clean up
        await bridge.disconnect()

    @pytest.mark.asyncio
    async def test_connect_timeout(self, bridge):
        """Test connection timeout."""

        async def timeout_coro(*args, **kwargs):
            raise asyncio.TimeoutError()

        with patch("asyncio.open_connection", side_effect=timeout_coro):
            with pytest.raises(AioComfoConnectTimeout, match="Timeout while connecting"):
                await bridge.connect(LOCAL_UUID)
        assert not bridge.is_connected()

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "error",
        [
            OSError(113, "No route to host"),
            ConnectionRefusedError(111, "Connection refused"),
            socket.gaierror("Name or service not known"),
        ],
    )
    async def test_connect_not_reachable(self, bridge, error):
        """Test that a bridge we can't reach doesn't raise a bare OSError."""

        async def error_coro(*args, **kwargs):
            raise error

        with patch("asyncio.open_connection", side_effect=error_coro):
            with pytest.raises(AioComfoConnectNotReachable, match="Could not connect to bridge"):
                await bridge.connect(LOCAL_UUID)
        assert not bridge.is_connected()

    @pytest.mark.asyncio
    async def test_connect_already_connected(self, bridge, mock_connection):
        """Test connecting when already connected."""
        mock_reader, mock_writer = mock_connection

        async def mock_read_messages():
            try:
                await asyncio.sleep(100)
            except asyncio.CancelledError:
                raise

        with patch("asyncio.open_connection", return_value=(mock_reader, mock_writer)):
            with patch.object(bridge, "_read_messages", side_effect=mock_read_messages):
                await bridge.connect(LOCAL_UUID)

        # Try to connect again
        with patch("asyncio.open_connection") as mock_connect:
            await bridge.connect(LOCAL_UUID)
            # Should not attempt to connect again
            mock_connect.assert_not_called()

        # Clean up
        await bridge.disconnect()

    @pytest.mark.asyncio
    async def test_disconnect(self, bridge, mock_connection):
        """Test disconnection."""
        mock_reader, mock_writer = mock_connection

        async def mock_read_messages():
            try:
                await asyncio.sleep(100)
            except asyncio.CancelledError:
                raise

        with patch("asyncio.open_connection", return_value=(mock_reader, mock_writer)):
            with patch.object(bridge, "_read_messages", side_effect=mock_read_messages):
                await bridge.connect(LOCAL_UUID)

        await bridge.disconnect()

        mock_writer.close.assert_called_once()
        mock_writer.wait_closed.assert_called_once()
        assert bridge._reader is None
        assert bridge._writer is None
        assert bridge._read_task is None

    @pytest.mark.asyncio
    async def test_disconnect_when_not_connected(self, bridge):
        """Test disconnecting when not connected."""
        # Should not raise any errors
        await bridge.disconnect()
        assert not bridge.is_connected()

    @pytest.mark.asyncio
    async def test_disconnect_cancels_read_task(self, bridge, mock_connection):
        """Test that disconnect cancels the read task."""
        mock_reader, mock_writer = mock_connection

        async def mock_read_messages():
            try:
                await asyncio.sleep(100)  # Long running task
            except asyncio.CancelledError:
                raise

        with patch("asyncio.open_connection", return_value=(mock_reader, mock_writer)):
            with patch.object(bridge, "_read_messages", side_effect=mock_read_messages):
                await bridge.connect(LOCAL_UUID)

        read_task = bridge._read_task
        assert not read_task.done()

        await bridge.disconnect()

        assert read_task.cancelled()

    @pytest.mark.asyncio
    async def test_send_when_not_connected(self, bridge):
        """Test sending when not connected."""
        from aiocomfoconnect.protobuf import zehnder_pb2

        with pytest.raises(AioComfoConnectNotConnected, match="Not connected"):
            await bridge._send(
                zehnder_pb2.KeepAlive,
                zehnder_pb2.GatewayOperation.KeepAliveType,
                reply=False,
            )

    @pytest.mark.asyncio
    async def test_send_success(self, bridge, mock_connection):
        """Test successful message sending."""
        mock_reader, mock_writer = mock_connection

        async def mock_read_messages():
            try:
                await asyncio.sleep(100)
            except asyncio.CancelledError:
                raise

        with patch("asyncio.open_connection", return_value=(mock_reader, mock_writer)):
            with patch.object(bridge, "_read_messages", side_effect=mock_read_messages):
                await bridge.connect(LOCAL_UUID)

        from aiocomfoconnect.protobuf import zehnder_pb2

        # Send a message that doesn't expect a reply
        result = await bridge._send(
            zehnder_pb2.KeepAlive,
            zehnder_pb2.GatewayOperation.KeepAliveType,
            reply=False,
        )

        assert result is None
        mock_writer.write.assert_called_once()
        mock_writer.drain.assert_called_once()

        # Clean up
        await bridge.disconnect()

    @pytest.mark.asyncio
    async def test_send_with_reply_timeout(self, bridge, mock_connection):
        """Test sending a message that expects a reply but times out."""
        mock_reader, mock_writer = mock_connection

        async def mock_read_messages():
            try:
                await asyncio.sleep(100)
            except asyncio.CancelledError:
                raise

        with patch("asyncio.open_connection", return_value=(mock_reader, mock_writer)):
            with patch.object(bridge, "_read_messages", side_effect=mock_read_messages):
                await bridge.connect(LOCAL_UUID)

        from aiocomfoconnect.protobuf import zehnder_pb2

        # Send a message that expects a reply but won't get one (with a short timeout for faster tests)
        with pytest.raises(AioComfoConnectTimeout, match="Timeout while waiting for response"):
            await bridge._send(
                zehnder_pb2.VersionRequest,
                zehnder_pb2.GatewayOperation.VersionRequestType,
                reply=True,
                timeout=0.01,
            )

        # Clean up
        await bridge.disconnect()

    @pytest.mark.asyncio
    async def test_send_connection_error(self, bridge, mock_connection):
        """Test sending when connection is lost during send."""
        mock_reader, mock_writer = mock_connection
        mock_writer.drain = AsyncMock(side_effect=ConnectionError("Connection lost"))

        async def mock_read_messages():
            try:
                await asyncio.sleep(100)
            except asyncio.CancelledError:
                raise

        with patch("asyncio.open_connection", return_value=(mock_reader, mock_writer)):
            with patch.object(bridge, "_read_messages", side_effect=mock_read_messages):
                await bridge.connect("00000000000000000000000000000001")

        from aiocomfoconnect.protobuf import zehnder_pb2

        with pytest.raises(AioComfoConnectNotConnected, match="Connection lost while sending"):
            await bridge._send(
                zehnder_pb2.KeepAlive,
                zehnder_pb2.GatewayOperation.KeepAliveType,
                reply=False,
            )

        # Clean up
        await bridge.disconnect()

    @pytest.mark.asyncio
    async def test_send_serializes_concurrent_calls(self, bridge, mock_connection):
        """Test that concurrent sends use unique references."""
        mock_reader, mock_writer = mock_connection

        first_drain_started = asyncio.Event()
        allow_first_drain = asyncio.Event()

        async def drain_side_effect():
            if not first_drain_started.is_set():
                first_drain_started.set()
                await allow_first_drain.wait()
            else:
                await asyncio.sleep(0)

        mock_writer.drain.side_effect = drain_side_effect

        async def mock_read_messages():
            try:
                await asyncio.sleep(100)
            except asyncio.CancelledError:
                raise

        with patch("asyncio.open_connection", return_value=(mock_reader, mock_writer)):
            with patch.object(bridge, "_read_messages", side_effect=mock_read_messages):
                await bridge.connect(LOCAL_UUID)

        from aiocomfoconnect.protobuf import zehnder_pb2

        assert bridge._local_uuid == LOCAL_UUID
        assert bridge.uuid == "00000000000000000000000000000001"

        first_send = asyncio.create_task(
            bridge._send(
                zehnder_pb2.KeepAlive,
                zehnder_pb2.GatewayOperation.KeepAliveType,
                reply=False,
            )
        )

        try:
            await asyncio.wait_for(first_drain_started.wait(), timeout=1)
            initial_write_calls = mock_writer.write.call_count

            send_two_started = asyncio.Event()

            async def run_second_send():
                send_two_started.set()
                await bridge._send(
                    zehnder_pb2.KeepAlive,
                    zehnder_pb2.GatewayOperation.KeepAliveType,
                    reply=False,
                )

            second_send = asyncio.create_task(run_second_send())

            await asyncio.wait_for(send_two_started.wait(), timeout=1)
            await asyncio.sleep(0)
            # With pipelining enabled, both sends complete concurrently
            # so both writes happen immediately
            assert mock_writer.write.call_count >= initial_write_calls + 1

            allow_first_drain.set()

            await asyncio.wait_for(asyncio.gather(first_send, second_send), timeout=1)
            assert mock_writer.write.call_count == initial_write_calls + 1
        finally:
            allow_first_drain.set()
            await asyncio.wait_for(bridge.disconnect(), timeout=1)

    @pytest.mark.asyncio
    async def test_disconnect_notifies_pending(self, bridge, mock_connection):
        """Test that pending listeners receive an exception on disconnect."""
        mock_reader, mock_writer = mock_connection

        async def mock_read_messages():
            try:
                await asyncio.sleep(100)
            except asyncio.CancelledError:
                raise

        with patch("asyncio.open_connection", return_value=(mock_reader, mock_writer)):
            with patch.object(bridge, "_read_messages", side_effect=mock_read_messages):
                await bridge.connect(LOCAL_UUID)

        assert bridge._event_bus is not None
        assert bridge._reference is not None
        pending_future = bridge._loop.create_future()
        test_reference = next(bridge._reference)
        bridge._event_bus.add_listener(test_reference, pending_future)

        await bridge.disconnect()

        assert pending_future.done()
        with pytest.raises(AioComfoConnectNotConnected):
            pending_future.result()

    @pytest.mark.asyncio
    async def test_read_messages_cancelled(self, bridge):
        """Test that _read_messages handles cancellation correctly."""
        # Set up minimal state for _read_messages to work
        bridge._reader = AsyncMock()
        bridge._reader.readexactly = AsyncMock(side_effect=asyncio.CancelledError())
        bridge._writer = MagicMock()
        bridge._writer.is_closing.return_value = False

        with pytest.raises(asyncio.CancelledError):
            await bridge._read_messages()

    @pytest.mark.asyncio
    async def test_read_messages_disconnected(self, bridge):
        """Test that _read_messages handles disconnection correctly."""
        with patch.object(bridge, "_process_message", side_effect=AioComfoConnectNotConnected("Test disconnect")):
            with pytest.raises(AioComfoConnectNotConnected):
                await bridge._read_messages()

    @pytest.mark.asyncio
    async def test_process_message_incomplete_read(self, bridge):
        """Test processing message when connection is closed during read."""
        mock_reader = AsyncMock()
        mock_reader.readexactly.side_effect = asyncio.IncompleteReadError(b"", 4)
        mock_writer = MagicMock()
        mock_writer.is_closing.return_value = False

        bridge._reader = mock_reader
        bridge._writer = mock_writer

        with pytest.raises(AioComfoConnectNotConnected, match="connection was closed"):
            await bridge._process_message()

    @pytest.mark.asyncio
    async def test_process_message_connection_error(self, bridge):
        """Test processing message when there's a connection error."""
        mock_reader = AsyncMock()
        mock_reader.readexactly.side_effect = ConnectionError("Network error")
        mock_writer = MagicMock()
        mock_writer.is_closing.return_value = False

        bridge._reader = mock_reader
        bridge._writer = mock_writer

        with pytest.raises(AioComfoConnectNotConnected, match="Connection error"):
            await bridge._process_message()

    @pytest.mark.asyncio
    async def test_callbacks(self, bridge):
        """Test that callbacks can be set."""
        sensor_callback = Mock()
        alarm_callback = Mock()

        bridge.set_sensor_callback(sensor_callback)
        bridge.set_alarm_callback(alarm_callback)

        assert bridge._Bridge__sensor_callback_fn == sensor_callback
        assert bridge._Bridge__alarm_callback_fn == alarm_callback

    def test_repr(self, bridge):
        """Test string representation."""
        repr_str = repr(bridge)
        assert "192.168.1.100" in repr_str
        assert "00000000000000000000000000000001" in repr_str


class TestBridgeNodeDiscovery:
    """Tests for the discovery of the ventilation unit node."""

    @pytest.fixture
    def bridge(self):
        """Create a connected-ish Bridge instance, ready to receive node notifications."""
        bridge = Bridge("192.168.1.100", LOCAL_UUID)
        bridge._ventilation_node_found = asyncio.Event()
        return bridge

    @pytest.mark.asyncio
    async def test_nodes_are_stored(self, bridge):
        """Test that announced nodes are stored by node id."""
        node_notification(bridge, node_id=1, product_id=ProductId.COMFOAIRQ)
        node_notification(bridge, node_id=48, product_id=ProductId.ZEHNDERGATEWAY, zone_id=255)

        assert bridge.nodes[1] == Node(node_id=1, product_id=ProductId.COMFOAIRQ, zone_id=1, mode=2)
        assert bridge.nodes[48].product_id == ProductId.ZEHNDERGATEWAY
        assert bridge.ventilation_node_id == 1

    @pytest.mark.asyncio
    async def test_ventilation_node_is_not_node_1(self, bridge):
        """Test a ComfoAir Flex setup, where the ventilation unit is not node 1."""
        node_notification(bridge, node_id=11, product_id=25)
        node_notification(bridge, node_id=41, product_id=ProductId.COMFOAIRFLEXCONNECTIONBOARD)
        node_notification(bridge, node_id=45, product_id=ProductId.COMFOAIRFLEX)

        assert bridge.ventilation_node_id == 45

    @pytest.mark.asyncio
    async def test_no_ventilation_node(self, bridge):
        """Test that nodes that don't accept RMI commands are never selected."""
        node_notification(bridge, node_id=41, product_id=ProductId.COMFOAIRFLEXCONNECTIONBOARD)
        node_notification(bridge, node_id=48, product_id=ProductId.ZEHNDERGATEWAY, zone_id=255)

        assert bridge.ventilation_node_id is None

    @pytest.mark.asyncio
    async def test_comfoclime_node(self, bridge):
        """Test that a ComfoClime on the bus is found, without becoming the ventilation unit."""
        node_notification(bridge, node_id=1, product_id=ProductId.COMFOAIRQ)
        node_notification(bridge, node_id=2, product_id=ProductId.COMFOCLIME, zone_id=3)

        assert bridge.comfoclime_node_id == 2
        assert bridge.comfoclime_zone_id == 3
        assert bridge.ventilation_node_id == 1

    @pytest.mark.asyncio
    async def test_no_comfoclime_node(self, bridge):
        """Test that comfoclime_node_id is None when there is no ComfoClime on the bus."""
        node_notification(bridge, node_id=1, product_id=ProductId.COMFOAIRQ)

        assert bridge.comfoclime_node_id is None
        assert bridge.comfoclime_zone_id is None

    @pytest.mark.asyncio
    async def test_offline_node_is_removed(self, bridge):
        """Test that a node that goes offline is forgotten."""
        node_notification(bridge, node_id=45, product_id=ProductId.COMFOAIRFLEX)
        assert bridge.ventilation_node_id == 45

        node_notification(bridge, node_id=45, product_id=ProductId.COMFOAIRFLEX, mode=zehnder_pb2.CnNodeNotification.NODE_OFFLINE)

        assert bridge.nodes == {}
        assert bridge.ventilation_node_id is None

    @pytest.mark.asyncio
    async def test_legacy_node_without_product_id_is_offline(self, bridge):
        """Test that a legacy node without a product id is considered offline."""
        node_notification(bridge, node_id=1, product_id=0, mode=zehnder_pb2.CnNodeNotification.NODE_LEGACY)

        assert bridge.nodes == {}

    @pytest.mark.asyncio
    async def test_wait_for_ventilation_node(self, bridge):
        """Test waiting for a ventilation unit that shows up."""

        async def announce():
            await asyncio.sleep(0.05)
            node_notification(bridge, node_id=45, product_id=ProductId.COMFOAIRFLEX)

        task = asyncio.create_task(announce())
        assert await bridge.wait_for_ventilation_node(timeout=5) == 45
        await task

    @pytest.mark.asyncio
    async def test_wait_for_ventilation_node_timeout(self, bridge):
        """Test waiting for a ventilation unit that never shows up."""
        with pytest.raises(VentilationUnitNotFoundException, match="did not announce a ventilation unit"):
            await bridge.wait_for_ventilation_node(timeout=0.05)

    @pytest.mark.asyncio
    async def test_wait_for_ventilation_node_ignores_other_nodes(self, bridge):
        """Test that other nodes don't end the wait for the ventilation unit."""
        node_notification(bridge, node_id=48, product_id=ProductId.ZEHNDERGATEWAY, zone_id=255)

        with pytest.raises(VentilationUnitNotFoundException):
            await bridge.wait_for_ventilation_node(timeout=0.05)

    @pytest.mark.asyncio
    async def test_rmi_request_uses_discovered_node(self, bridge):
        """Test that RMI requests are sent to the discovered ventilation unit."""
        node_notification(bridge, node_id=45, product_id=ProductId.COMFOAIRFLEX)

        with patch.object(bridge, "is_connected", return_value=True), patch.object(bridge, "_send", MagicMock()) as mock_send:
            bridge.cmd_rmi_request(b"\x01\x01\x01\x10\x08")

        assert mock_send.call_args[0][2]["nodeId"] == 45

    @pytest.mark.asyncio
    async def test_rmi_request_honours_explicit_node(self, bridge):
        """Test that an explicit node id overrules the discovered ventilation unit."""
        node_notification(bridge, node_id=45, product_id=ProductId.COMFOAIRFLEX)

        with patch.object(bridge, "is_connected", return_value=True), patch.object(bridge, "_send", MagicMock()) as mock_send:
            bridge.cmd_rmi_request(b"\x01\x01\x01\x10\x08", node_id=11)

        assert mock_send.call_args[0][2]["nodeId"] == 11

    @pytest.mark.asyncio
    async def test_rmi_request_without_ventilation_node(self, bridge):
        """Test that RMI requests are refused when we don't know where the ventilation unit is."""
        node_notification(bridge, node_id=48, product_id=ProductId.ZEHNDERGATEWAY, zone_id=255)

        with patch.object(bridge, "is_connected", return_value=True), patch.object(bridge, "_send", MagicMock()) as mock_send:
            with pytest.raises(VentilationUnitNotFoundException, match="has not announced a ventilation unit"):
                bridge.cmd_rmi_request(b"\x01\x01\x01\x10\x08")

        mock_send.assert_not_called()

    @pytest.mark.asyncio
    async def test_rmi_request_when_not_connected(self, bridge):
        """Test that RMI requests report the missing connection, not the missing ventilation unit."""
        # The node table is empty while disconnected, like after disconnect().
        with patch.object(bridge, "_send", MagicMock()) as mock_send:
            with pytest.raises(AioComfoConnectNotConnected, match="Not connected"):
                bridge.cmd_rmi_request(b"\x01\x01\x01\x10\x08")

        mock_send.assert_not_called()

    @pytest.mark.asyncio
    async def test_rmi_request_when_not_connected_with_explicit_node(self, bridge):
        """Test that RMI requests to an explicit node are refused while disconnected too."""
        with patch.object(bridge, "_send", MagicMock()) as mock_send:
            with pytest.raises(AioComfoConnectNotConnected, match="Not connected"):
                bridge.cmd_rmi_request(b"\x01\x01\x01\x10\x08", node_id=11)

        mock_send.assert_not_called()

    @pytest.mark.asyncio
    async def test_nodes_are_reset_on_connect(self, bridge, mock_connection):
        """Test that the nodes of a previous session are forgotten when we reconnect."""
        node_notification(bridge, node_id=45, product_id=ProductId.COMFOAIRFLEX)

        async def mock_read_messages():
            await asyncio.sleep(100)

        with patch("asyncio.open_connection", return_value=mock_connection):
            with patch.object(bridge, "_read_messages", side_effect=mock_read_messages):
                await bridge.connect(LOCAL_UUID)

        assert bridge.nodes == {}
        assert bridge.ventilation_node_id is None

        await bridge.disconnect()

    @pytest.mark.asyncio
    async def test_node_notification_is_dispatched(self, bridge):
        """Test that a CnNodeNotification message ends up in the node list."""
        cmd = zehnder_pb2.GatewayOperation()
        cmd.type = zehnder_pb2.GatewayOperation.CnNodeNotificationType
        msg = zehnder_pb2.CnNodeNotification()
        msg.nodeId = 45
        msg.productId = ProductId.COMFOAIRFLEX
        msg.zoneId = 1
        msg.mode = zehnder_pb2.CnNodeNotification.NODE_NORMAL

        with patch.object(bridge, "_read", AsyncMock(return_value=Message(cmd, msg, LOCAL_UUID, LOCAL_UUID))):
            await bridge._process_message()

        assert bridge.ventilation_node_id == 45


class TestBridgeRegister:
    """Tests for Bridge.register()."""

    @pytest.fixture
    def lanc_bridge(self):
        """A Bridge with bridge_type=0 (LAN C, the default)."""
        return Bridge("192.168.1.100", LOCAL_UUID, bridge_type=0)

    @pytest.fixture
    def pro_bridge(self):
        """A Bridge with bridge_type=GATEWAY_TYPE_PRO."""
        return Bridge("192.168.1.100", LOCAL_UUID, bridge_type=GATEWAY_TYPE_PRO)

    @pytest.mark.asyncio
    async def test_lanc_already_registered(self, lanc_bridge):
        """LAN C: session starts successfully → already registered, no cmd_register_app call."""
        with (
            patch.object(lanc_bridge, "_open_connection", new_callable=AsyncMock) as mock_open,
            patch.object(lanc_bridge, "cmd_start_session", new_callable=AsyncMock) as mock_session,
            patch.object(lanc_bridge, "cmd_register_app", new_callable=AsyncMock) as mock_register,
        ):

            result = await lanc_bridge.register(LOCAL_UUID, "test-app", 1234)

        assert result is False
        mock_open.assert_called_once_with(LOCAL_UUID)
        mock_session.assert_called_once_with(True)
        mock_register.assert_not_called()

    @pytest.mark.asyncio
    async def test_lanc_not_registered(self, lanc_bridge):
        """LAN C: session returns NotAllowed → registers then starts session, returns True."""
        with (
            patch.object(lanc_bridge, "_open_connection", new_callable=AsyncMock) as mock_open,
            patch.object(lanc_bridge, "cmd_start_session", new_callable=AsyncMock) as mock_session,
            patch.object(lanc_bridge, "cmd_register_app", new_callable=AsyncMock) as mock_register,
        ):

            mock_session.side_effect = [ComfoConnectNotAllowed("not registered"), None]

            result = await lanc_bridge.register(LOCAL_UUID, "test-app", 1234)

        assert result is True
        mock_open.assert_called_once_with(LOCAL_UUID)
        mock_register.assert_called_once_with(LOCAL_UUID, "test-app", 1234)
        assert mock_session.call_count == 2

    @pytest.mark.asyncio
    async def test_lanc_wrong_pin(self, lanc_bridge):
        """LAN C: not registered, wrong PIN → cmd_register_app fails, exception propagates."""
        with (
            patch.object(lanc_bridge, "_open_connection", new_callable=AsyncMock),
            patch.object(lanc_bridge, "cmd_start_session", new_callable=AsyncMock) as mock_session,
            patch.object(lanc_bridge, "cmd_register_app", new_callable=AsyncMock) as mock_register,
        ):

            mock_session.side_effect = ComfoConnectNotAllowed("not registered")
            mock_register.side_effect = ComfoConnectNotAllowed("wrong pin")

            with pytest.raises(ComfoConnectNotAllowed):
                await lanc_bridge.register(LOCAL_UUID, "test-app", 9999)

        mock_session.assert_called_once_with(True)  # checked once, not retried after failed register
        mock_register.assert_called_once_with(LOCAL_UUID, "test-app", 9999)

    @pytest.mark.asyncio
    async def test_pro_registers_directly_without_session_check(self, pro_bridge):
        """Pro: skips the session-first check, calls cmd_register_app then cmd_start_session."""
        call_order = []

        async def track_register(*args):
            call_order.append("register")

        async def track_session(*args):
            call_order.append("session")

        with (
            patch.object(pro_bridge, "_open_connection", new_callable=AsyncMock) as mock_open,
            patch.object(pro_bridge, "cmd_register_app", side_effect=track_register) as mock_register,
            patch.object(pro_bridge, "cmd_start_session", side_effect=track_session) as mock_session,
        ):

            result = await pro_bridge.register(LOCAL_UUID, "test-app", 1234)

        assert result is True
        mock_open.assert_called_once_with(LOCAL_UUID)
        mock_register.assert_called_once_with(LOCAL_UUID, "test-app", 1234)
        mock_session.assert_called_once_with(True)
        assert call_order == ["register", "session"]

    @pytest.mark.asyncio
    async def test_pro_wrong_pin(self, pro_bridge):
        """Pro: cmd_register_app fails with wrong PIN → exception propagates, session never started."""
        with (
            patch.object(pro_bridge, "_open_connection", new_callable=AsyncMock),
            patch.object(pro_bridge, "cmd_register_app", new_callable=AsyncMock) as mock_register,
            patch.object(pro_bridge, "cmd_start_session", new_callable=AsyncMock) as mock_session,
        ):

            mock_register.side_effect = ComfoConnectNotAllowed("wrong pin")

            with pytest.raises(ComfoConnectNotAllowed):
                await pro_bridge.register(LOCAL_UUID, "test-app", 9999)

        mock_session.assert_not_called()


class TestGatewayTypeFromSession:
    """Tests for recognising a ComfoConnect Pro when the session starts."""

    @pytest.mark.asyncio
    async def test_lanc_session(self):
        """A LAN C leaves the devicename of the session confirmation empty, so the type stays LAN C."""
        bridge = Bridge("192.168.1.100", LOCAL_UUID)
        with patch.object(bridge, "_send", AsyncMock(return_value=zehnder_pb2.StartSessionConfirm())):
            await bridge.cmd_start_session(True)

        assert bridge.bridge_type == GatewayType.LANC

    @pytest.mark.asyncio
    async def test_pro_session(self):
        """A Pro identifies itself with devicename "ccpro", also when it wasn't found by discovery."""
        bridge = Bridge("192.168.1.100", LOCAL_UUID)

        with patch.object(bridge, "_send", AsyncMock(return_value=zehnder_pb2.StartSessionConfirm(devicename="ccpro"))) as mock_send:
            reply = await bridge.cmd_start_session(True)

        assert bridge.bridge_type == GatewayType.PRO
        assert reply.devicename == "ccpro"
        assert mock_send.call_args[0][2] == {"takeover": True}

    @pytest.mark.asyncio
    async def test_discovered_type_is_kept(self):
        """A session without "ccpro" keeps the type from discovery, e.g. the WiFi module of a ComfoAir Flex."""
        bridge = Bridge("192.168.1.100", LOCAL_UUID, bridge_type=GatewayType.SEASON)
        with patch.object(bridge, "_send", AsyncMock(return_value=zehnder_pb2.StartSessionConfirm())):
            await bridge.cmd_start_session(True)

        assert bridge.bridge_type == GatewayType.SEASON


def _frame(cmd_type, msg=None):
    """Encode a frame like the bridge sends it, including the 4 byte length prefix."""
    cmd = zehnder_pb2.GatewayOperation()
    cmd.type = cmd_type
    return Message(cmd, msg or zehnder_pb2.KeepAlive(), LOCAL_UUID, LOCAL_UUID).encode()


def _raw_frame(cmd_buf):
    """Encode a frame with a hand-made command, for values the protobuf classes refuse to encode."""
    packet = bytes.fromhex(LOCAL_UUID) + bytes.fromhex(LOCAL_UUID) + len(cmd_buf).to_bytes(2, byteorder="big") + cmd_buf
    return len(packet).to_bytes(4, byteorder="big") + packet


def _sensor_frame(pdid, value):
    """Encode a CnRpdoNotification frame for a sensor."""
    return _frame(zehnder_pb2.GatewayOperation.CnRpdoNotificationType, zehnder_pb2.CnRpdoNotification(pdid=pdid, data=bytes([value])))


class TestReadLoopResilience:
    """Bad messages and failing callbacks must not end the read loop, only transport errors may."""

    @staticmethod
    async def run_read_loop(bridge, *frames):
        """Feed the frames to the bridge and run the read loop until the stream ends."""
        bridge._reader = asyncio.StreamReader()
        for frame in frames:
            bridge._reader.feed_data(frame)
        bridge._reader.feed_eof()

        # The end of the stream is a transport error, the only way the loop may end.
        with pytest.raises(AioComfoConnectNotConnected, match="connection was closed"):
            await bridge._read_messages()

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "cmd_type",
        [
            zehnder_pb2.GatewayOperation.NoOperation,
            zehnder_pb2.GatewayOperation.CnWhoAmIConfirmType,
            zehnder_pb2.GatewayOperation.WiFiNetworksConfirmType,
            200,  # Not in the enum at all
        ],
    )
    async def test_unknown_message_type_is_skipped(self, cmd_type, caplog):
        """A message type without a mapping is skipped with a debug log."""
        bridge = Bridge("192.168.1.100", LOCAL_UUID)
        received = Mock()
        bridge.set_sensor_callback(received)

        if cmd_type in zehnder_pb2.GatewayOperation.OperationType.values():
            frame = _frame(cmd_type)
        else:
            # Field 1 (type) with the varint 200, which protobuf doesn't let us encode since it's not in the enum
            assert cmd_type == 200
            frame = _raw_frame(bytes([0x08, 0xC8, 0x01]))

        with caplog.at_level("DEBUG", logger="aiocomfoconnect.bridge"):
            await self.run_read_loop(bridge, frame, _sensor_frame(276, 42))

        received.assert_called_once_with(276, 42)
        assert any(r.levelname == "DEBUG" and "unknown type" in r.getMessage() for r in caplog.records)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("length", [0, 20, 33])
    async def test_short_packet_is_skipped(self, length, caplog):
        """A packet shorter than the header is skipped with a warning."""
        bridge = Bridge("192.168.1.100", LOCAL_UUID)
        received = Mock()
        bridge.set_sensor_callback(received)

        short_frame = length.to_bytes(4, byteorder="big") + bytes(length)
        await self.run_read_loop(bridge, short_frame, _sensor_frame(276, 42))

        received.assert_called_once_with(276, 42)
        assert any(r.levelname == "WARNING" and "shorter than" in r.getMessage() for r in caplog.records)

    @pytest.mark.asyncio
    async def test_sensor_callback_exception_is_logged(self, caplog):
        """An exception in the sensor callback is logged and the next message is still processed."""
        bridge = Bridge("192.168.1.100", LOCAL_UUID)
        received = Mock(side_effect=[RuntimeError("boom"), None])
        bridge.set_sensor_callback(received)

        await self.run_read_loop(bridge, _sensor_frame(276, 1), _sensor_frame(276, 2))

        assert received.call_args_list == [((276, 1),), ((276, 2),)]
        errors = [r for r in caplog.records if r.levelname == "ERROR" and r.exc_info]
        assert len(errors) == 1
        assert isinstance(errors[0].exc_info[1], RuntimeError)

    @pytest.mark.asyncio
    async def test_alarm_callback_exception_is_logged(self, caplog):
        """An exception in the alarm callback is logged and the next message is still processed."""
        bridge = Bridge("192.168.1.100", LOCAL_UUID)
        bridge.set_alarm_callback(Mock(side_effect=RuntimeError("boom")))
        received = Mock()
        bridge.set_sensor_callback(received)

        alarm = _frame(zehnder_pb2.GatewayOperation.CnAlarmNotificationType, zehnder_pb2.CnAlarmNotification(nodeId=1))
        await self.run_read_loop(bridge, alarm, _sensor_frame(276, 42))

        received.assert_called_once_with(276, 42)
        assert any(r.levelname == "ERROR" and isinstance(r.exc_info[1], RuntimeError) for r in caplog.records if r.exc_info)

    @pytest.mark.asyncio
    async def test_value_fn_exception_is_logged(self, caplog):
        """An exception in a sensor's value_fn is logged and the next message is still processed."""
        received = Mock()
        comfoconnect = ComfoConnect("192.168.1.100", LOCAL_UUID, sensor_callback=received, sensor_delay=0)
        comfoconnect._sensors[276] = create_sensor(sensor_id=276, value_fn=lambda value: 1 / 0)
        comfoconnect._sensors[277] = create_sensor(sensor_id=277)

        await self.run_read_loop(comfoconnect, _sensor_frame(276, 1), _sensor_frame(277, 2))

        received.assert_called_once_with(comfoconnect._sensors[277], 2)
        assert any(isinstance(r.exc_info[1], ZeroDivisionError) for r in caplog.records if r.exc_info)


class FakeBridgeServer:
    """A bridge on localhost that hands each connection to a handler, to test what happens on the real transport."""

    def __init__(self, handler):
        self.handler = handler
        self.connections = 0
        self.server = None

    async def __aenter__(self):
        self.server = await asyncio.start_server(self._handle, "127.0.0.1", 0)
        return self

    async def __aexit__(self, *exc_info):
        self.server.close()
        self.server.close_clients()
        await self.server.wait_closed()

    @property
    def port(self):
        return self.server.sockets[0].getsockname()[1]

    def bridge(self):
        bridge = Bridge("127.0.0.1", LOCAL_UUID)
        bridge.PORT = self.port
        return bridge

    async def _handle(self, reader, writer):
        self.connections += 1
        try:
            await self.handler(reader, writer)
        except (ConnectionError, asyncio.IncompleteReadError):
            pass
        finally:
            writer.close()

    @staticmethod
    async def read_request(reader):
        """Read the next request a client sends."""
        length = int.from_bytes(await reader.readexactly(4), byteorder="big")
        return Message.decode(await reader.readexactly(length))

    @staticmethod
    def reply(writer, request, cmd_type, msg, result=zehnder_pb2.GatewayOperation.OK):
        """Send a reply to a request."""
        cmd = zehnder_pb2.GatewayOperation()
        cmd.type = cmd_type
        cmd.reference = request.cmd.reference
        cmd.result = result
        writer.write(Message(cmd, msg, LOCAL_UUID, LOCAL_UUID).encode())


def _collect_loop_errors():
    """Collect the errors the event loop reports, like "Task exception was never retrieved"."""
    reports = []
    asyncio.get_running_loop().set_exception_handler(lambda _loop, context: reports.append(context))
    return reports


async def _wait_for_read_task(bridge):
    """Wait until the read loop of the bridge has ended."""
    await asyncio.wait({bridge._read_task}, timeout=2)
    assert bridge._read_task.done()


class TestConnectionLifecycle:
    """When the read loop ends, the connection is closed and pending requests fail right away."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("ending", ["eof", "close_session"])
    async def test_read_loop_end_closes_connection(self, ending):
        """A pending request fails at once, new requests fail at once, and connect() works again without disconnect()."""
        unretrieved = _collect_loop_errors()
        session_started = asyncio.Event()

        async def handler(reader, writer):
            if server.connections == 1:
                await server.read_request(reader)  # The request that never gets a reply
                if ending == "close_session":
                    writer.write(_frame(zehnder_pb2.GatewayOperation.CloseSessionRequestType, zehnder_pb2.CloseSessionRequest()))
                    await writer.drain()
                    await reader.read()  # The bridge waits for us to close the connection
                return
            request = await server.read_request(reader)
            server.reply(writer, request, zehnder_pb2.GatewayOperation.StartSessionConfirmType, zehnder_pb2.StartSessionConfirm())
            await writer.drain()
            session_started.set()
            await reader.read()

        async with FakeBridgeServer(handler) as server:
            bridge = server.bridge()
            await bridge.connect(LOCAL_UUID)

            loop = asyncio.get_running_loop()
            start = loop.time()
            with pytest.raises(AioComfoConnectNotConnected):
                await bridge._send(zehnder_pb2.VersionRequest, zehnder_pb2.GatewayOperation.VersionRequestType, timeout=5)
            assert loop.time() - start < 1

            await _wait_for_read_task(bridge)
            assert not bridge.is_connected()
            assert bridge._event_bus.listeners == {}
            with pytest.raises(AioComfoConnectNotConnected):
                await bridge.cmd_version_request()

            # Reconnect without disconnect() first
            await bridge.connect(LOCAL_UUID)
            assert server.connections == 2
            assert bridge.is_connected()
            await bridge.cmd_start_session(True)
            assert session_started.is_set()

            await bridge.disconnect()
            assert not bridge.is_connected()

        assert unretrieved == []

    @pytest.mark.asyncio
    async def test_disconnect_after_read_loop_ended(self):
        """disconnect() cleans up after a read loop that already ended, and retrieves its exception."""
        unretrieved = _collect_loop_errors()

        async def handler(reader, writer):
            return  # Close the connection right away

        async with FakeBridgeServer(handler) as server:
            bridge = server.bridge()
            await bridge.connect(LOCAL_UUID)
            read_task = bridge._read_task
            await _wait_for_read_task(bridge)

            await bridge.disconnect()

        assert bridge._read_task is None
        assert bridge._writer is None
        assert bridge._event_bus is None
        assert read_task.done()
        del read_task
        gc.collect()
        assert unretrieved == []

    @pytest.mark.asyncio
    async def test_disconnect_when_closing_fails(self, bridge_with_writer):
        """disconnect() still clears its state when waiting for the connection to close raises."""
        bridge = bridge_with_writer
        bridge._writer.wait_closed = AsyncMock(side_effect=ConnectionResetError("reset"))

        await bridge.disconnect()

        assert bridge._writer is None
        assert bridge._event_bus is None

    @pytest.fixture
    def bridge_with_writer(self):
        """A bridge with a mocked open connection and no read loop."""
        bridge = Bridge("192.168.1.100", LOCAL_UUID)
        bridge._writer = MagicMock()
        bridge._writer.is_closing.return_value = False
        bridge._writer.drain = AsyncMock()
        bridge._writer.wait_closed = AsyncMock()
        bridge._reference = iter(range(1, 100))
        bridge._event_bus = EventBus()
        bridge._local_uuid = LOCAL_UUID
        return bridge

    @pytest.mark.asyncio
    async def test_reply_removes_listener(self, bridge_with_writer):
        """A request that gets its reply leaves nothing behind in the listener table."""
        bridge = bridge_with_writer
        task = asyncio.create_task(bridge.cmd_version_request())
        await asyncio.sleep(0)
        assert list(bridge._event_bus.listeners) == [1]

        bridge._event_bus.emit(1, zehnder_pb2.VersionConfirm())
        await task

        assert bridge._event_bus.listeners == {}

    @pytest.mark.asyncio
    async def test_timeout_removes_listener(self, bridge_with_writer):
        """A request that times out leaves nothing behind in the listener table."""
        bridge = bridge_with_writer
        with pytest.raises(AioComfoConnectTimeout):
            await bridge._send(zehnder_pb2.VersionRequest, zehnder_pb2.GatewayOperation.VersionRequestType, timeout=0.01)

        assert bridge._event_bus.listeners == {}

    @pytest.mark.asyncio
    async def test_cancel_removes_listener(self, bridge_with_writer):
        """A request that is cancelled leaves nothing behind in the listener table."""
        bridge = bridge_with_writer
        task = asyncio.create_task(bridge.cmd_version_request())
        await asyncio.sleep(0)
        assert bridge._event_bus.listeners != {}

        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        assert bridge._event_bus.listeners == {}

    @pytest.mark.asyncio
    async def test_send_failure(self, bridge_with_writer):
        """A send failure raises AioComfoConnectNotConnected and sets no exception on a future that nobody awaits."""
        bridge = bridge_with_writer
        bridge._writer.drain = AsyncMock(side_effect=ConnectionResetError("reset"))
        futures = []
        add_listener = bridge._event_bus.add_listener
        bridge._event_bus.add_listener = lambda reference, fut: (futures.append(fut), add_listener(reference, fut))

        with pytest.raises(AioComfoConnectNotConnected, match="while sending"):
            await bridge.cmd_version_request()

        assert bridge._event_bus.listeners == {}
        # An exception on it would be logged as "Future exception was never retrieved"
        assert len(futures) == 1 and not futures[0].done()

    @pytest.mark.asyncio
    async def test_unmatched_error_reply_is_logged(self, caplog):
        """An error reply for a request that nobody waits for anymore is logged."""
        bridge = Bridge("192.168.1.100", LOCAL_UUID)
        bridge._event_bus = EventBus()
        cmd = zehnder_pb2.GatewayOperation()
        cmd.type = zehnder_pb2.GatewayOperation.CnRmiResponseType
        cmd.reference = 42
        cmd.result = zehnder_pb2.GatewayOperation.NOT_ALLOWED
        bridge._reader = asyncio.StreamReader()
        bridge._reader.feed_data(Message(cmd, zehnder_pb2.CnRmiResponse(), LOCAL_UUID, LOCAL_UUID).encode())

        await bridge._process_message()

        assert any(r.levelname == "WARNING" and "without a matching request" in r.getMessage() for r in caplog.records)
