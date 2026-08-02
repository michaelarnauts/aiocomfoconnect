"""Tests for the Bridge class."""

import asyncio
import socket
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from aiocomfoconnect.bridge import GATEWAY_TYPE_PRO, Bridge, EventBus, Message, Node
from aiocomfoconnect.const import ProductId
from aiocomfoconnect.protobuf import zehnder_pb2
from tests.conftest import node_notification

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

        # Send a message that expects a reply but won't get one (with 0.5s timeout for faster tests)
        with pytest.raises(AioComfoConnectTimeout, match="Timeout while waiting for response"):
            await bridge._send(
                zehnder_pb2.VersionRequest,
                zehnder_pb2.GatewayOperation.VersionRequestType,
                reply=True,
                timeout=0.5,
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

    @pytest.mark.asyncio
    async def test_cmd_methods(self, bridge):
        """Test that command methods exist and have correct signatures."""
        # Just verify the methods exist
        assert hasattr(bridge, "cmd_start_session")
        assert hasattr(bridge, "cmd_close_session")
        assert hasattr(bridge, "cmd_list_registered_apps")
        assert hasattr(bridge, "cmd_register_app")
        assert hasattr(bridge, "cmd_deregister_app")
        assert hasattr(bridge, "cmd_version_request")
        assert hasattr(bridge, "cmd_time_request")
        assert hasattr(bridge, "cmd_node_request")
        assert hasattr(bridge, "cmd_rmi_request")
        assert hasattr(bridge, "cmd_rpdo_request")
        assert hasattr(bridge, "cmd_keepalive")

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

        with patch.object(bridge, "_send", MagicMock()) as mock_send:
            bridge.cmd_rmi_request(b"\x01\x01\x01\x10\x08")

        assert mock_send.call_args[0][2]["nodeId"] == 45

    @pytest.mark.asyncio
    async def test_rmi_request_honours_explicit_node(self, bridge):
        """Test that an explicit node id overrules the discovered ventilation unit."""
        node_notification(bridge, node_id=45, product_id=ProductId.COMFOAIRFLEX)

        with patch.object(bridge, "_send", MagicMock()) as mock_send:
            bridge.cmd_rmi_request(b"\x01\x01\x01\x10\x08", node_id=11)

        assert mock_send.call_args[0][2]["nodeId"] == 11

    @pytest.mark.asyncio
    async def test_rmi_request_without_ventilation_node(self, bridge):
        """Test that RMI requests are refused when we don't know where the ventilation unit is."""
        node_notification(bridge, node_id=48, product_id=ProductId.ZEHNDERGATEWAY, zone_id=255)

        with patch.object(bridge, "_send", MagicMock()) as mock_send:
            with pytest.raises(VentilationUnitNotFoundException, match="has not announced a ventilation unit"):
                bridge.cmd_rmi_request(b"\x01\x01\x01\x10\x08")

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
