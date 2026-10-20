"""Tests for the Bridge class."""

import asyncio
import gc
from unittest.mock import AsyncMock, MagicMock, Mock, call, patch

import pytest

from aiocomfoconnect.bridge import Bridge, Message, Node
from aiocomfoconnect.comfoconnect import ComfoConnect
from aiocomfoconnect.const import GatewayType, ProductId
from aiocomfoconnect.protobuf import zehnder_pb2
from tests.conftest import create_sensor, node_notification

LOCAL_UUID = "00000000000000000000000000000001"

from aiocomfoconnect.exceptions import (
    AioComfoConnectNotConnected,
    AioComfoConnectTimeout,
    ComfoConnectBadRequest,
    ComfoConnectInternalError,
    ComfoConnectNoResources,
    ComfoConnectNotAllowed,
    ComfoConnectNotExist,
    ComfoConnectNotReachable,
    ComfoConnectOtherSession,
    ComfoConnectRmiError,
    VentilationUnitNotFoundException,
)


async def test_connect_timeout():
    """A bridge that doesn't accept the connection in time raises AioComfoConnectTimeout."""

    async def timeout_coro(*args, **kwargs):
        raise asyncio.TimeoutError()

    bridge = Bridge("192.168.1.100", LOCAL_UUID)
    with patch("asyncio.open_connection", side_effect=timeout_coro):
        with pytest.raises(AioComfoConnectTimeout, match="Timeout while connecting"):
            await bridge.connect(LOCAL_UUID)
    assert not bridge.is_connected()


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

    @pytest.mark.parametrize(
        ("nodes", "expected"),
        [
            ([(48, ProductId.ZEHNDERGATEWAY)], 48),
            ([(20, ProductId.COMFOCONNECTPRO)], 20),
            # The WiFi connection module built into a ComfoAir Flex.
            ([(41, ProductId.COMFOAIRFLEXCONNECTIONBOARD)], 41),
            # A ComfoAir Flex with a LAN C has both, and then it's the LAN C.
            ([(41, ProductId.COMFOAIRFLEXCONNECTIONBOARD), (48, ProductId.ZEHNDERGATEWAY)], 48),
            ([(7, ProductId.CO2SENSOR)], None),
        ],
    )
    @pytest.mark.asyncio
    async def test_bridge_node(self, bridge, nodes, expected):
        """Test that the bridge finds its own node among the others."""
        node_notification(bridge, node_id=1, product_id=ProductId.COMFOAIRQ)
        for node_id, product_id in nodes:
            node_notification(bridge, node_id=node_id, product_id=product_id)

        assert (bridge.bridge_node.node_id if bridge.bridge_node else None) == expected

    @pytest.mark.asyncio
    async def test_node_callback(self, bridge):
        """Test that the node callback gets every announced node, also when it goes offline."""
        announced = []
        bridge.set_node_callback(announced.append)

        node_notification(bridge, node_id=7, product_id=ProductId.CO2SENSOR)
        node_notification(bridge, node_id=7, product_id=ProductId.CO2SENSOR, mode=zehnder_pb2.CnNodeNotification.NODE_OFFLINE)

        assert [(node.node_id, node.is_offline) for node in announced] == [(7, False), (7, True)]
        assert bridge.nodes == {}

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

    async def test_nodes_are_reset_on_connect(self, bridge, fake_bridge):
        """Test that the nodes of a previous session are forgotten when we reconnect."""
        node_notification(bridge, node_id=45, product_id=ProductId.COMFOAIRFLEX)
        bridge.host = "127.0.0.1"
        await bridge.connect(LOCAL_UUID)

        assert bridge.nodes == {}
        assert bridge.ventilation_node_id is None
        await bridge.disconnect()

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


class TestBridgeRegister:
    """Tests for Bridge.register()."""

    @pytest.mark.parametrize("bridge_type", [GatewayType.LANC, GatewayType.SEASON, GatewayType.PRO])
    @pytest.mark.asyncio
    async def test_registers_then_starts_session(self, bridge_type):
        """Every bridge registers directly, also when the app is registered already, and then starts a session."""
        bridge = Bridge("192.168.1.100", LOCAL_UUID, bridge_type=bridge_type)
        calls = Mock()
        calls.attach_mock(AsyncMock(), "register")
        calls.attach_mock(AsyncMock(), "session")
        with (
            patch.object(bridge, "_open_connection", new_callable=AsyncMock) as mock_open,
            patch.object(bridge, "cmd_register_app", calls.register),
            patch.object(bridge, "cmd_start_session", calls.session),
        ):
            await bridge.register(LOCAL_UUID, "test-app", 1234)

        mock_open.assert_awaited_once_with(LOCAL_UUID)
        assert calls.mock_calls == [call.register(LOCAL_UUID, "test-app", 1234), call.session()]

    @pytest.mark.asyncio
    async def test_wrong_pin(self):
        """A wrong PIN fails the registration, and no session is started."""
        bridge = Bridge("192.168.1.100", LOCAL_UUID)
        with (
            patch.object(bridge, "_open_connection", new_callable=AsyncMock),
            patch.object(bridge, "cmd_register_app", new_callable=AsyncMock, side_effect=ComfoConnectNotAllowed("wrong pin")),
            patch.object(bridge, "cmd_start_session", new_callable=AsyncMock) as mock_session,
        ):
            with pytest.raises(ComfoConnectNotAllowed):
                await bridge.register(LOCAL_UUID, "test-app", 9999)

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


class TestResultCodes:
    """Test how the result code of a reply is turned into an exception for the request that waits for it."""

    @staticmethod
    async def reply(frame):
        """Read a reply to the request with reference 42, and return the future of that request."""
        bridge = Bridge("192.168.1.100", LOCAL_UUID)
        future = asyncio.get_running_loop().create_future()
        bridge._pending[42] = future
        await _run_read_loop(bridge, frame)
        return future

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "result,exception",
        [
            ("BAD_REQUEST", ComfoConnectBadRequest),
            ("INTERNAL_ERROR", ComfoConnectInternalError),
            ("NOT_REACHABLE", ComfoConnectNotReachable),
            ("OTHER_SESSION", ComfoConnectOtherSession),
            ("NOT_ALLOWED", ComfoConnectNotAllowed),
            ("NO_RESOURCES", ComfoConnectNoResources),
            ("NOT_EXIST", ComfoConnectNotExist),
            ("RMI_ERROR", ComfoConnectRmiError),
        ],
    )
    async def test_error_result_raises(self, result, exception):
        """Every error result raises its own exception, with the message attached."""
        cmd = zehnder_pb2.GatewayOperation(type=zehnder_pb2.GatewayOperation.CnRmiResponseType, reference=42)
        cmd.result = zehnder_pb2.GatewayOperation.GatewayResult.Value(result)
        future = await self.reply(Message(cmd, zehnder_pb2.CnRmiResponse(), LOCAL_UUID, LOCAL_UUID).encode())

        with pytest.raises(exception) as exc_info:
            future.result()

        assert type(exc_info.value) is exception
        assert exc_info.value.message.cmd.reference == 42

    @pytest.mark.asyncio
    async def test_unknown_result_returns_the_message(self):
        """A result code that isn't in the enum is treated like OK."""
        # Field 1 (type) with CnRmiResponseType (34), field 2 (result) with 99, which isn't in the enum, and field 4 (reference) with 42.
        future = await self.reply(_raw_frame(bytes([0x08, 0x22, 0x10, 0x63, 0x20, 0x2A])))
        assert isinstance(future.result(), zehnder_pb2.CnRmiResponse)


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


async def _run_read_loop(bridge, *frames):
    """Feed the frames to the bridge and run the read loop until the stream ends."""
    bridge._reader = asyncio.StreamReader()
    for frame in frames:
        bridge._reader.feed_data(frame)
    bridge._reader.feed_eof()

    # The end of the stream is a transport error, the only way the loop may end.
    with pytest.raises(AioComfoConnectNotConnected, match="connection was closed"):
        await bridge._read_messages()


class TestReadLoopResilience:
    """Bad messages and failing callbacks must not end the read loop, only transport errors may."""

    @pytest.mark.asyncio
    async def test_invalid_protobuf_is_skipped(self, caplog):
        """A packet whose command isn't valid protobuf is skipped with an error log."""
        bridge = Bridge("192.168.1.100", LOCAL_UUID)
        received = Mock()
        bridge.set_sensor_callback(received)

        await _run_read_loop(bridge, _raw_frame(b"\xff\xff\xff"), _sensor_frame(276, 42))

        received.assert_called_once_with(276, 42)
        assert any(r.levelname == "ERROR" and "Failed to decode" in r.getMessage() for r in caplog.records)

    @pytest.mark.asyncio
    async def test_connection_error_ends_the_loop(self):
        """A connection error ends the loop, closes the connection and fails the pending requests."""
        bridge = Bridge("192.168.1.100", LOCAL_UUID)
        bridge._reader = AsyncMock()
        bridge._reader.readexactly.side_effect = ConnectionResetError("reset")
        bridge._writer = MagicMock()
        pending = asyncio.get_running_loop().create_future()
        bridge._pending[1] = pending

        with pytest.raises(AioComfoConnectNotConnected, match="Connection error"):
            await bridge._read_messages()

        bridge._writer.close.assert_called_once()
        with pytest.raises(AioComfoConnectNotConnected, match="Connection error"):
            pending.result()

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
            await _run_read_loop(bridge, frame, _sensor_frame(276, 42))

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
        await _run_read_loop(bridge, short_frame, _sensor_frame(276, 42))

        received.assert_called_once_with(276, 42)
        assert any(r.levelname == "WARNING" and "shorter than" in r.getMessage() for r in caplog.records)

    @pytest.mark.asyncio
    async def test_sensor_callback_exception_is_logged(self, caplog):
        """An exception in the sensor callback is logged and the next message is still processed."""
        bridge = Bridge("192.168.1.100", LOCAL_UUID)
        received = Mock(side_effect=[RuntimeError("boom"), None])
        bridge.set_sensor_callback(received)

        await _run_read_loop(bridge, _sensor_frame(276, 1), _sensor_frame(276, 2))

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
        await _run_read_loop(bridge, alarm, _sensor_frame(276, 42))

        received.assert_called_once_with(276, 42)
        assert any(r.levelname == "ERROR" and isinstance(r.exc_info[1], RuntimeError) for r in caplog.records if r.exc_info)

    @pytest.mark.asyncio
    async def test_value_fn_exception_is_logged(self, caplog):
        """An exception in a sensor's value_fn is logged and the next message is still processed."""
        received = Mock()
        comfoconnect = ComfoConnect("192.168.1.100", LOCAL_UUID, sensor_callback=received, sensor_delay=0)
        comfoconnect._sensors[276] = create_sensor(sensor_id=276, value_fn=lambda value: 1 / 0)
        comfoconnect._sensors[277] = create_sensor(sensor_id=277)

        await _run_read_loop(comfoconnect, _sensor_frame(276, 1), _sensor_frame(277, 2))

        received.assert_called_once_with(comfoconnect._sensors[277], 2)
        assert any(isinstance(r.exc_info[1], ZeroDivisionError) for r in caplog.records if r.exc_info)


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
    async def test_read_loop_end_closes_connection(self, fake_bridge, ending):
        """A pending request fails at once, new requests fail at once, and connect() works again without disconnect()."""
        unretrieved = _collect_loop_errors()
        bridge = Bridge("127.0.0.1", LOCAL_UUID)
        await bridge.connect(LOCAL_UUID)

        # The fake bridge doesn't answer a VersionRequest, so this request waits until the connection ends.
        loop = asyncio.get_running_loop()
        start = loop.time()
        pending = asyncio.create_task(bridge._send(zehnder_pb2.VersionRequest, zehnder_pb2.GatewayOperation.VersionRequestType, timeout=5))
        await fake_bridge.wait_for(lambda: fake_bridge.received(zehnder_pb2.GatewayOperation.VersionRequestType))
        if ending == "eof":
            fake_bridge.drop()
        else:
            fake_bridge.close_session()
        with pytest.raises(AioComfoConnectNotConnected):
            await pending
        assert loop.time() - start < 1

        await _wait_for_read_task(bridge)
        assert not bridge.is_connected()
        assert bridge._pending == {}
        with pytest.raises(AioComfoConnectNotConnected):
            await bridge.cmd_version_request()

        # Reconnect without disconnect() first
        await bridge.connect(LOCAL_UUID)
        assert fake_bridge.connections == 2
        assert bridge.is_connected()
        await bridge.cmd_start_session(True)
        assert fake_bridge.received(zehnder_pb2.GatewayOperation.StartSessionRequestType, connection=2)

        await bridge.disconnect()
        assert not bridge.is_connected()
        assert unretrieved == []

    @pytest.mark.asyncio
    async def test_disconnect_after_read_loop_ended(self, fake_bridge):
        """disconnect() cleans up after a read loop that already ended, and retrieves its exception."""
        unretrieved = _collect_loop_errors()
        bridge = Bridge("127.0.0.1", LOCAL_UUID)
        await bridge.connect(LOCAL_UUID)
        read_task = bridge._read_task
        fake_bridge.drop()
        await _wait_for_read_task(bridge)

        await bridge.disconnect()

        assert bridge._read_task is None
        assert bridge._writer is None
        assert bridge._pending == {}
        assert read_task.done()
        del read_task
        gc.collect()
        assert unretrieved == []

    @pytest.mark.asyncio
    async def test_cancelled_disconnect(self, fake_bridge):
        """A disconnect() that is cancelled while it waits for the read loop raises CancelledError."""
        bridge = Bridge("127.0.0.1", LOCAL_UUID)
        await bridge.connect(LOCAL_UUID)

        disconnect_task = asyncio.create_task(bridge.disconnect())
        await asyncio.sleep(0)
        disconnect_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await disconnect_task

        await bridge.disconnect()
        assert not bridge.is_connected()

    @pytest.mark.asyncio
    async def test_disconnect_when_closing_fails(self, bridge_with_writer):
        """disconnect() still clears its state when waiting for the connection to close raises."""
        bridge = bridge_with_writer
        bridge._writer.wait_closed = AsyncMock(side_effect=ConnectionResetError("reset"))

        await bridge.disconnect()

        assert bridge._writer is None
        assert bridge._pending == {}

    @pytest.fixture
    def bridge_with_writer(self):
        """A bridge with a mocked open connection and no read loop."""
        bridge = Bridge("192.168.1.100", LOCAL_UUID)
        bridge._writer = MagicMock()
        bridge._writer.is_closing.return_value = False
        bridge._writer.drain = AsyncMock()
        bridge._writer.wait_closed = AsyncMock()
        bridge._reference = iter(range(1, 100))
        bridge._local_uuid = LOCAL_UUID
        return bridge

    @pytest.mark.asyncio
    async def test_reply_removes_pending(self, bridge_with_writer):
        """A request that gets its reply leaves nothing behind in the pending table."""
        bridge = bridge_with_writer
        task = asyncio.create_task(bridge.cmd_version_request())
        await asyncio.sleep(0)
        assert list(bridge._pending) == [1]

        assert bridge._resolve(1, zehnder_pb2.VersionConfirm())
        await task

        assert bridge._pending == {}

    @pytest.mark.asyncio
    async def test_timeout_removes_pending(self, bridge_with_writer):
        """A request that times out leaves nothing behind in the pending table."""
        bridge = bridge_with_writer
        with pytest.raises(AioComfoConnectTimeout):
            await bridge._send(zehnder_pb2.VersionRequest, zehnder_pb2.GatewayOperation.VersionRequestType, timeout=0.01)

        assert bridge._pending == {}

    @pytest.mark.asyncio
    async def test_cancel_removes_pending(self, bridge_with_writer):
        """A request that is cancelled leaves nothing behind in the pending table."""
        bridge = bridge_with_writer
        task = asyncio.create_task(bridge.cmd_version_request())
        await asyncio.sleep(0)
        assert bridge._pending != {}

        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        assert bridge._pending == {}

    @pytest.mark.asyncio
    async def test_send_failure(self, bridge_with_writer):
        """A send failure raises AioComfoConnectNotConnected and sets no exception on a future that nobody awaits."""
        bridge = bridge_with_writer
        bridge._writer.drain = AsyncMock(side_effect=ConnectionResetError("reset"))
        futures = []
        bridge._writer.write = lambda _data: futures.extend(bridge._pending.values())

        with pytest.raises(AioComfoConnectNotConnected, match="while sending"):
            await bridge.cmd_version_request()

        assert bridge._pending == {}
        # An exception on it would be logged as "Future exception was never retrieved"
        assert len(futures) == 1 and not futures[0].done()


class TestPendingRequests:
    """Every request waits for the reply with its own reference, until the connection ends."""

    @pytest.mark.asyncio
    async def test_concurrent_requests_get_their_own_reply(self, fake_bridge):
        """Replies are matched to their request by reference, also when they arrive in another order."""
        fake_bridge.rmi_responses = {b"\x01": b"\x0a", b"\x02": b"\x0b"}
        fake_bridge.withhold = {zehnder_pb2.GatewayOperation.CnRmiRequestType}
        bridge = Bridge("127.0.0.1", LOCAL_UUID)
        await bridge.connect(LOCAL_UUID)

        first = asyncio.create_task(bridge.cmd_rmi_request(b"\x01", node_id=1))
        second = asyncio.create_task(bridge.cmd_rmi_request(b"\x02", node_id=1))
        await fake_bridge.wait_for(lambda: len(fake_bridge.rmi_requests) == 2)
        fake_bridge._pending.reverse()
        fake_bridge.answer_pending()

        assert (await first).message == b"\x0a"
        assert (await second).message == b"\x0b"
        await bridge.disconnect()

    @pytest.mark.asyncio
    async def test_disconnect_fails_pending_request(self, fake_bridge):
        """disconnect() fails a request that is still waiting for its reply."""
        unretrieved = _collect_loop_errors()
        bridge = Bridge("127.0.0.1", LOCAL_UUID)
        await bridge.connect(LOCAL_UUID)

        # The fake bridge doesn't answer a VersionRequest.
        pending = asyncio.create_task(bridge.cmd_version_request())
        await fake_bridge.wait_for(lambda: fake_bridge.received(zehnder_pb2.GatewayOperation.VersionRequestType))
        await bridge.disconnect()

        with pytest.raises(AioComfoConnectNotConnected, match="Disconnected"):
            await pending
        assert unretrieved == []

    @pytest.mark.asyncio
    async def test_late_reply_is_ignored(self, fake_bridge):
        """A reply that arrives after its request timed out is dropped, and the connection keeps working."""
        fake_bridge.withhold = {zehnder_pb2.GatewayOperation.CnTimeRequestType}
        bridge = Bridge("127.0.0.1", LOCAL_UUID)
        await bridge.connect(LOCAL_UUID)

        with pytest.raises(AioComfoConnectTimeout):
            await bridge._send(zehnder_pb2.CnTimeRequest, zehnder_pb2.GatewayOperation.CnTimeRequestType, timeout=0.01)
        fake_bridge.withhold = set()
        fake_bridge.answer_pending()

        assert (await bridge.cmd_time_request()).currentTime == 1
        assert bridge.is_connected()
        await bridge.disconnect()

    @pytest.mark.asyncio
    async def test_late_error_reply_is_logged(self, fake_bridge, caplog):
        """An error reply that arrives after its request timed out is logged, and the connection keeps working."""
        fake_bridge.rmi_responses = {b"\x01": zehnder_pb2.GatewayOperation.RMI_ERROR}
        fake_bridge.withhold = {zehnder_pb2.GatewayOperation.CnRmiRequestType}
        bridge = Bridge("127.0.0.1", LOCAL_UUID)
        await bridge.connect(LOCAL_UUID)

        with pytest.raises(AioComfoConnectTimeout):
            await bridge._send(zehnder_pb2.CnRmiRequest, zehnder_pb2.GatewayOperation.CnRmiRequestType, {"nodeId": 1, "message": b"\x01"}, timeout=0.01)
        fake_bridge.withhold = set()
        fake_bridge.answer_pending()

        assert (await bridge.cmd_time_request()).currentTime == 1
        assert any(r.levelname == "WARNING" and "without a matching request" in r.getMessage() for r in caplog.records)
        await bridge.disconnect()
