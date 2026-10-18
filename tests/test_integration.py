"""Tests of the connection, the reconnects and the sensors against a fake bridge that speaks the real protocol."""

import asyncio
import socket

import pytest

from aiocomfoconnect.bridge import Bridge
from aiocomfoconnect.const import ERRORS, ProductId
from aiocomfoconnect.exceptions import (
    AioComfoConnectNotConnected,
    AioComfoConnectNotReachable,
    AioComfoConnectTimeout,
    ComfoConnectBadRequest,
    ComfoConnectNotAllowed,
    ComfoConnectRmiError,
    VentilationUnitNotFoundException,
)
from tests.conftest import create_sensor
from tests.fake_bridge import BRIDGE_UUID, GO, LOCAL_UUID

GET_SPEED = bytes([0x83, 0x15, 0x01, 0x01])


async def assert_stays_disconnected(fake_bridge, client):
    """Check that the client is disconnected, and doesn't connect again by itself."""
    assert not client.is_connected()
    assert client._reconnect_task is None
    connections = fake_bridge.connections
    # Give a reconnect the time to happen. The back-off is 10 ms in tests.
    await asyncio.sleep(0.05)
    assert fake_bridge.connections == connections
    assert not client.is_connected()


async def roundtrip(client):
    """Wait until the client has processed everything the fake bridge sent before."""
    await client.cmd_time_request()


class TestConnect:
    """Connecting and starting a session."""

    async def test_bridge_lifecycle(self, fake_bridge):
        """The Bridge connects, talks to the bridge and disconnects."""
        bridge = Bridge("127.0.0.1", BRIDGE_UUID)
        await bridge.connect(LOCAL_UUID)
        assert bridge.is_connected()

        await bridge.cmd_start_session(True)
        assert (await bridge.cmd_time_request()).currentTime == 1

        await bridge.disconnect()
        assert not bridge.is_connected()
        assert fake_bridge.connections == 1

    async def test_connect(self, fake_bridge, make_client):
        """connect() starts a session, finds the ventilation unit and keeps the connection up."""
        client = make_client()
        await client.connect(LOCAL_UUID)

        assert client.is_connected()
        assert client.ventilation_node_id == 1
        assert [msg.takeover for msg in fake_bridge.received(GO.StartSessionRequestType)] == [True]
        assert len(fake_bridge.received(GO.CnNodeRequestType)) == 1
        assert not client._reconnect_task.done()

        # Connecting again while connected does nothing.
        await client.connect(LOCAL_UUID)
        assert fake_bridge.connections == 1

    async def test_connect_waits_for_session(self, fake_bridge, make_client):
        """connect() doesn't return before the bridge accepted the session."""
        fake_bridge.withhold = {GO.StartSessionRequestType}
        client = make_client()
        connect_task = asyncio.create_task(client.connect(LOCAL_UUID))

        await fake_bridge.wait_for(lambda: fake_bridge.received(GO.StartSessionRequestType))
        await asyncio.sleep(0.01)
        assert not connect_task.done()

        fake_bridge.answer_pending()
        await connect_task
        assert client.is_connected()

    async def test_connect_discovers_ventilation_node(self, fake_bridge, make_client):
        """RMI requests go to the ventilation unit the bridge announced, which isn't always node 1."""
        fake_bridge.nodes = [(41, ProductId.COMFOAIRFLEXCONNECTIONBOARD, 1), (45, ProductId.COMFOAIRFLEX, 1)]
        fake_bridge.rmi_responses[GET_SPEED] = bytes.fromhex("0100000000ffffffffffffffff02")
        client = make_client()
        await client.connect(LOCAL_UUID)

        assert client.ventilation_node_id == 45
        assert await client.get_speed() == "medium"
        assert fake_bridge.received(GO.CnRmiRequestType)[0].nodeId == 45

    async def test_connect_without_ventilation_unit(self, fake_bridge, make_client):
        """connect() fails when the bridge doesn't announce a ventilation unit, and doesn't retry."""
        fake_bridge.nodes = [(48, ProductId.ZEHNDERGATEWAY, 255)]
        client = make_client()

        with pytest.raises(VentilationUnitNotFoundException):
            await client.connect(LOCAL_UUID)

        assert client.ventilation_node_id is None
        await assert_stays_disconnected(fake_bridge, client)

    async def test_connect_timeout(self, fake_bridge, make_client):
        """connect() gives up after connect_timeout when the bridge doesn't answer, and stops retrying."""
        fake_bridge.silent = True
        client = make_client(connect_timeout=0.1)

        with pytest.raises(AioComfoConnectTimeout, match="Failed to connect within 0.1 seconds"):
            await client.connect(LOCAL_UUID)

        await assert_stays_disconnected(fake_bridge, client)

    @pytest.mark.parametrize(
        ("session_result", "error"),
        [(GO.NOT_ALLOWED, ComfoConnectNotAllowed), (GO.BAD_REQUEST, ComfoConnectBadRequest)],
    )
    async def test_connect_error(self, fake_bridge, make_client, session_result, error):
        """connect() raises the error of the bridge right away, without retrying."""
        fake_bridge.session_result = session_result
        client = make_client()

        with pytest.raises(error):
            await client.connect(LOCAL_UUID)

        await assert_stays_disconnected(fake_bridge, client)

    async def test_connect_not_reachable(self, fake_bridge, make_client, monkeypatch):
        """connect() raises right away when nothing listens on the port, without retrying."""
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            monkeypatch.setattr(Bridge, "PORT", sock.getsockname()[1])
        client = make_client()

        with pytest.raises(AioComfoConnectNotReachable):
            await client.connect(LOCAL_UUID)

        assert client._reconnect_task is None

    async def test_connect_cancelled(self, fake_bridge, make_client):
        """A cancelled connect() closes the connection and doesn't reconnect later."""
        fake_bridge.withhold = {GO.StartSessionRequestType}
        client = make_client()
        connect_task = asyncio.create_task(client.connect(LOCAL_UUID))
        await fake_bridge.wait_for(lambda: fake_bridge.received(GO.StartSessionRequestType))

        connect_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await connect_task

        await assert_stays_disconnected(fake_bridge, client)

    async def test_disconnect_during_connect(self, fake_bridge, make_client):
        """disconnect() makes a connect() that is still busy fail right away, and nothing reconnects."""
        fake_bridge.withhold = {GO.StartSessionRequestType}
        client = make_client(connect_timeout=5)
        connect_task = asyncio.create_task(client.connect(LOCAL_UUID))
        await fake_bridge.wait_for(lambda: fake_bridge.received(GO.StartSessionRequestType))

        async with asyncio.timeout(1):
            await client.disconnect()
            with pytest.raises(AioComfoConnectNotConnected):
                await connect_task

        await assert_stays_disconnected(fake_bridge, client)

    async def test_concurrent_connect(self, fake_bridge, make_client):
        """A second connect() while the first is busy waits until the session is ready, and doesn't connect again."""
        fake_bridge.withhold = {GO.StartSessionRequestType}
        client = make_client()
        first = asyncio.create_task(client.connect(LOCAL_UUID))
        await fake_bridge.wait_for(lambda: fake_bridge.received(GO.StartSessionRequestType))
        second = asyncio.create_task(client.connect(LOCAL_UUID))
        await asyncio.sleep(0.01)
        assert not second.done()

        fake_bridge.answer_pending()
        await asyncio.gather(first, second)
        assert client.is_connected()
        assert fake_bridge.connections == 1


class TestReconnect:
    """Losing the connection and getting it back."""

    @pytest.mark.parametrize("lose_connection", ["drop", "close_session"])
    async def test_reconnect(self, fake_bridge, make_client, lose_connection):
        """The client reconnects and starts a new session every time the connection is lost."""
        client = make_client()
        await client.connect(LOCAL_UUID)

        for connection in (2, 3):
            getattr(fake_bridge, lose_connection)()
            await fake_bridge.wait_for(lambda: fake_bridge.received(GO.CnNodeRequestType, connection))
            await fake_bridge.wait_for(client.is_connected)

        assert fake_bridge.connections == 3
        assert len(fake_bridge.received(GO.StartSessionRequestType)) == 3
        fake_bridge.rmi_responses[GET_SPEED] = bytes.fromhex("0100000000ffffffffffffffff01")
        assert await client.get_speed() == "low"

    async def test_reconnect_retries(self, fake_bridge, make_client):
        """The client keeps trying when reconnecting fails."""
        client = make_client()
        await client.connect(LOCAL_UUID)

        fake_bridge.session_result = GO.BAD_REQUEST
        fake_bridge.drop()
        await fake_bridge.wait_for(lambda: fake_bridge.connections >= 3)
        fake_bridge.session_result = GO.OK
        await fake_bridge.wait_for(lambda: fake_bridge.received(GO.CnNodeRequestType, fake_bridge.connections))
        await fake_bridge.wait_for(client.is_connected)
        await roundtrip(client)

    async def test_heartbeat(self, fake_bridge, make_client):
        """With a heartbeat, the client asks the time while the connection is idle, and keeps the connection."""
        client = make_client(heartbeat_interval=0.02)
        await client.connect(LOCAL_UUID)

        await fake_bridge.wait_for(lambda: len(fake_bridge.received(GO.CnTimeRequestType)) >= 3)
        assert fake_bridge.connections == 1
        assert client.is_connected()

    async def test_heartbeat_reconnects_silent_bridge(self, fake_bridge, make_client):
        """When the bridge stops answering without closing the connection, the heartbeat closes it and the client reconnects."""
        client = make_client(heartbeat_interval=0.02)
        await client.connect(LOCAL_UUID)

        fake_bridge.silent = True
        await fake_bridge.wait_for(lambda: fake_bridge.received(GO.CnTimeRequestType, 1))
        fake_bridge.silent = False

        await fake_bridge.wait_for(lambda: fake_bridge.received(GO.CnNodeRequestType, 2))
        await fake_bridge.wait_for(client.is_connected)
        await roundtrip(client)
        assert fake_bridge.connections == 2

    async def test_no_heartbeat_by_default(self, fake_bridge, make_client):
        """Without a heartbeat, the client doesn't send anything while the connection is idle."""
        client = make_client()
        await client.connect(LOCAL_UUID)

        await asyncio.sleep(0.05)
        assert not fake_bridge.received(GO.CnTimeRequestType)

    async def test_disconnect(self, fake_bridge, make_client):
        """disconnect() closes the connection and stops reconnecting."""
        client = make_client()
        await client.connect(LOCAL_UUID)

        await client.disconnect()

        await assert_stays_disconnected(fake_bridge, client)

        with pytest.raises(AioComfoConnectNotConnected):
            await client.get_speed()

    async def test_disconnect_when_not_connected(self, make_client):
        """disconnect() without a connection doesn't raise."""
        client = make_client()
        await client.disconnect()
        assert not client.is_connected()

    async def test_cancelled_disconnect(self, fake_bridge, make_client):
        """A cancelled disconnect() raises CancelledError, and the connection is still closed."""
        client = make_client()
        await client.connect(LOCAL_UUID)

        disconnect_task = asyncio.create_task(client.disconnect())
        await asyncio.sleep(0)
        disconnect_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await disconnect_task

        await fake_bridge.wait_for(lambda: not client.is_connected())
        await asyncio.sleep(0.05)
        assert fake_bridge.connections == 1

    async def test_sensors_resubscribed_after_reconnect(self, fake_bridge, make_client):
        """The sensors are subscribed again on the new session."""
        client = make_client()
        await client.connect(LOCAL_UUID)
        await client.register_sensor(create_sensor(sensor_id=276))
        await client.register_sensor(create_sensor(sensor_id=277, sensor_type=2))

        fake_bridge.drop()
        await fake_bridge.wait_for(lambda: len(fake_bridge.received(GO.CnRpdoRequestType, 2)) == 2)

        assert [(msg.pdid, msg.type) for msg in fake_bridge.received(GO.CnRpdoRequestType, 2)] == [(276, 1), (277, 2)]

    async def test_failing_sensor_does_not_block_session(self, fake_bridge, make_client):
        """A sensor the bridge rejects after a reconnect doesn't stop the other sensors or the session."""
        client = make_client()
        await client.connect(LOCAL_UUID)
        await client.register_sensor(create_sensor(sensor_id=276))
        await client.register_sensor(create_sensor(sensor_id=277))

        fake_bridge.rpdo_results[276] = GO.BAD_REQUEST
        fake_bridge.drop()
        await fake_bridge.wait_for(lambda: len(fake_bridge.received(GO.CnRpdoRequestType, 2)) == 2)
        await fake_bridge.wait_for(client.is_connected)
        await roundtrip(client)

        assert set(client._sensors) == {276, 277}

    async def test_register_sensor_while_resubscribing(self, fake_bridge, make_client):
        """Registering a sensor while the sensors are subscribed again doesn't break the session."""
        client = make_client()
        await client.connect(LOCAL_UUID)
        await client.register_sensor(create_sensor(sensor_id=276))

        fake_bridge.withhold = {GO.CnRpdoRequestType}
        fake_bridge.drop()
        await fake_bridge.wait_for(lambda: fake_bridge.received(GO.CnRpdoRequestType, 2))
        register_task = asyncio.create_task(client.register_sensor(create_sensor(sensor_id=277)))
        await fake_bridge.wait_for(lambda: len(fake_bridge.received(GO.CnRpdoRequestType, 2)) == 2)

        fake_bridge.withhold = set()
        fake_bridge.answer_pending()
        await register_task
        await asyncio.sleep(0.05)  # The reconnect loop would fail and reconnect by now if the new sensor broke it.

        assert set(client._sensors) == {276, 277}
        assert client.is_connected()
        assert fake_bridge.connections == 2


class TestSensors:
    """Subscribing to sensors and receiving their values."""

    async def test_register_and_deregister_sensor(self, fake_bridge, make_client):
        """A sensor is subscribed with its type, and unsubscribed with a timeout of 0."""
        client = make_client()
        await client.connect(LOCAL_UUID)
        sensor = create_sensor(sensor_id=276, sensor_type=1)

        await client.register_sensor(sensor)
        assert client._sensors == {276: sensor}

        await client.deregister_sensor(sensor)
        assert client._sensors == {}
        assert 276 not in client._sensors_values

        subscribe, unsubscribe = fake_bridge.received(GO.CnRpdoRequestType)
        assert (subscribe.pdid, subscribe.type, subscribe.HasField("timeout")) == (276, 1, False)
        assert (unsubscribe.pdid, unsubscribe.type, unsubscribe.timeout) == (276, 1, 0)

    async def test_register_sensor_rejected(self, fake_bridge, make_client):
        """A sensor the bridge rejects is not kept, so it isn't subscribed again on every reconnect."""
        fake_bridge.rpdo_results[276] = GO.BAD_REQUEST
        client = make_client(sensor_delay=5)
        await client.connect(LOCAL_UUID)

        with pytest.raises(ComfoConnectBadRequest):
            await client.register_sensor(create_sensor(sensor_id=276))

        assert 276 not in client._sensors
        assert 276 not in client._sensors_values
        assert 276 not in client._sensor_holds

    async def test_register_sensors_concurrently(self, fake_bridge, make_client):
        """Many sensors can be subscribed at the same time."""
        client = make_client()
        await client.connect(LOCAL_UUID)

        await asyncio.gather(*[client.register_sensor(create_sensor(sensor_id=i)) for i in range(10)])

        assert len(client._sensors) == 10
        assert sorted(msg.pdid for msg in fake_bridge.received(GO.CnRpdoRequestType)) == list(range(10))

    async def test_sensor_values(self, fake_bridge, make_client):
        """Sensor values from the bridge reach the callback, converted by the value_fn of the sensor."""
        values = []
        client = make_client(sensor_callback=lambda sensor, value: values.append((sensor.id, value)))
        await client.connect(LOCAL_UUID)
        await client.register_sensor(create_sensor(sensor_id=276))
        await client.register_sensor(create_sensor(sensor_id=277, sensor_type=2, value_fn=lambda value: value / 10))

        fake_bridge.push_sensor(276, bytes([42]))
        fake_bridge.push_sensor(277, (215).to_bytes(2, "little"))
        await roundtrip(client)

        assert values == [(276, 42), (277, 21.5)]

    async def test_sensor_hold(self, fake_bridge, make_client):
        """The zero value the bridge sends right after subscribing is held back, and emitted when the hold expires."""
        values = []
        client = make_client(sensor_callback=lambda sensor, value: values.append(value), sensor_delay=0.05)
        await client.connect(LOCAL_UUID)
        await client.register_sensor(create_sensor(sensor_id=276))

        fake_bridge.push_sensor(276, bytes([0]))
        await roundtrip(client)
        assert not values

        await fake_bridge.wait_for(lambda: values)
        assert values == [0]

    async def test_sensor_hold_released_on_valid_value(self, fake_bridge, make_client):
        """A non-zero value ends the hold right away, and the expired hold doesn't emit the value again."""
        values = []
        client = make_client(sensor_callback=lambda sensor, value: values.append(value), sensor_delay=0.1)
        await client.connect(LOCAL_UUID)
        await client.register_sensor(create_sensor(sensor_id=276))

        fake_bridge.push_sensor(276, bytes([0]))
        fake_bridge.push_sensor(276, bytes([69]))
        fake_bridge.push_sensor(276, bytes([0]))
        await roundtrip(client)
        assert values == [69, 0]
        assert 276 not in client._sensor_holds

        await asyncio.sleep(0.15)
        assert values == [69, 0]

    async def test_sensor_hold_after_reconnect(self, fake_bridge, make_client):
        """The sensors are held again after a reconnect, since the bridge sends zero values for the new subscription."""
        values = []
        client = make_client(sensor_callback=lambda sensor, value: values.append(value), sensor_delay=5)
        await client.connect(LOCAL_UUID)
        await client.register_sensor(create_sensor(sensor_id=276))
        fake_bridge.push_sensor(276, bytes([69]))
        await roundtrip(client)
        assert values == [69]

        fake_bridge.drop()
        await fake_bridge.wait_for(lambda: fake_bridge.received(GO.CnRpdoRequestType, 2))
        await fake_bridge.wait_for(client.is_connected)

        fake_bridge.push_sensor(276, bytes([0]))
        fake_bridge.push_sensor(276, bytes([70]))
        await roundtrip(client)
        assert values == [69, 70]

    async def test_alarm(self, fake_bridge, make_client):
        """An alarm of the ventilation unit reaches the callback with its error messages."""
        alarms = []
        client = make_client(alarm_callback=lambda node_id, errors: alarms.append((node_id, errors)))
        await client.connect(LOCAL_UUID)

        fake_bridge.push_alarm(1, b"\x00\x00\x00\x00\x00\x00\x10\x00")  # Bit 52
        await roundtrip(client)

        assert alarms == [(1, {52: ERRORS[52]})]


class TestRmi:
    """RMI requests over the wire."""

    async def test_rmi_error(self, fake_bridge, make_client):
        """An RMI error of the unit is raised to the caller, and the session stays up."""
        fake_bridge.rmi_responses[GET_SPEED] = GO.RMI_ERROR
        client = make_client()
        await client.connect(LOCAL_UUID)

        with pytest.raises(ComfoConnectRmiError):
            await client.get_speed()

        assert client.is_connected()
        assert fake_bridge.rmi_requests == [GET_SPEED]
