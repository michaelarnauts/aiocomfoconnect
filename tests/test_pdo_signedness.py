"""PDO notifications preserve the signedness of their registered type."""

import asyncio
from unittest.mock import AsyncMock, Mock, patch

import pytest

from aiocomfoconnect.bridge import Bridge, Message
from aiocomfoconnect.comfoconnect import ComfoConnect
from aiocomfoconnect.const import PdoType
from aiocomfoconnect.protobuf import zehnder_pb2
from aiocomfoconnect.sensors import SENSOR_AVOIDED_HEATING_TOTAL, SENSORS

UUID = "00000000000000000000000000000001"


def feed_notification(bridge, pdid, data):
    """Feed the normal protobuf frame through the bridge's stream reader."""
    bridge._reader = asyncio.StreamReader()
    packet = Message(
        zehnder_pb2.GatewayOperation(type=zehnder_pb2.GatewayOperation.CnRpdoNotificationType),
        zehnder_pb2.CnRpdoNotification(pdid=pdid, data=data),
        UUID,
        UUID,
    ).encode()
    bridge._reader.feed_data(packet)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "pdo_type,data,expected",
    [
        (PdoType.TYPE_CN_UINT8, b"\x80", 128),
        (PdoType.TYPE_CN_UINT16, b"\x00\x80", 32768),
        (PdoType.TYPE_CN_UINT16, b"\xff\xff", 65535),
        (PdoType.TYPE_CN_UINT32, b"\x00\x00\x00\x80", 2147483648),
        (PdoType.TYPE_CN_INT8, b"\x80", -128),
        (PdoType.TYPE_CN_INT16, b"\xec\xff", -20),
        (PdoType.TYPE_CN_INT64, b"\xff" * 8, -1),
        (None, b"\x80", -128),
    ],
)
async def test_notification_uses_registered_signedness_before_request_ack(pdo_type, data, expected):
    """Early notifications use the requested type; unsolicited frames retain legacy decoding."""
    bridge = Bridge("127.0.0.1", UUID)
    received = Mock()
    bridge.set_sensor_callback(received)
    feed_notification(bridge, 215, data)

    async def send(*_args, **_kwargs):
        # The gateway may start sending data before acknowledging the subscription.
        await bridge._process_message()

    if pdo_type is None:
        await bridge._process_message()
    else:
        with patch.object(bridge, "_send", side_effect=send):
            await bridge.cmd_rpdo_request(215, pdo_type)
    received.assert_called_once_with(215, expected)


@pytest.mark.asyncio
async def test_unsigned_energy_total_reaches_the_library_sensor_callback():
    """A real unsigned energy sensor cannot publish a negative high counter value."""
    received = Mock()
    bridge = ComfoConnect("127.0.0.1", UUID, sensor_callback=received, sensor_delay=0)
    sensor = SENSORS[SENSOR_AVOIDED_HEATING_TOTAL]
    with patch.object(bridge, "_send", new=AsyncMock()):
        await bridge.register_sensor(sensor)
    feed_notification(bridge, sensor.id, b"\x00\x80")
    await bridge._process_message()
    received.assert_called_once_with(sensor, 32768)
