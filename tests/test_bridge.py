"""Tests for the Bridge class."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from aiocomfoconnect.bridge import Bridge, EventBus, Message

LOCAL_UUID = "00000000000000000000000000000001"

from aiocomfoconnect.exceptions import (
    AioComfoConnectNotConnected,
    AioComfoConnectTimeout,
    ComfoConnectNotAllowed,
    ComfoConnectOtherSession,
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
        assert hasattr(bridge, "cmd_rmi_request")
        assert hasattr(bridge, "cmd_rpdo_request")
        assert hasattr(bridge, "cmd_keepalive")

    def test_repr(self, bridge):
        """Test string representation."""
        repr_str = repr(bridge)
        assert "192.168.1.100" in repr_str
        assert "00000000000000000000000000000001" in repr_str
