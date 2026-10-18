"""Tests for the ComfoConnect class."""

from unittest.mock import AsyncMock, Mock, patch

import pytest

from aiocomfoconnect.comfoconnect import ComfoConnect, TimerEntry
from aiocomfoconnect.const import ERRORS_BASE, SCHEDULE_PRESET, TIMER_BOOST, PdoType, ProductId
from aiocomfoconnect import properties
from aiocomfoconnect.exceptions import (
    AioComfoConnectNotConnected,
    ComfoClimeNotFoundException,
    NodeNotFoundException,
    VentilationUnitNotFoundException,
)
from aiocomfoconnect.properties import (
    PROPERTY_CLIME_HEATING_COMFORT_TEMP,
    PROPERTY_CLIME_HEATPUMP_STANDBY,
    PROPERTY_CLIME_SEASON,
    PROPERTY_RMOT_HEATING_THRESHOLD,
    PROPERTY_SERIAL_NUMBER,
    PROPERTY_TEMPERATURE_PROFILE_MODE,
    Property,
)
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

    @pytest.mark.asyncio
    async def test_rmi_request_without_ventilation_node(self, comfoconnect):
        """Test that RMI commands are refused instead of being sent to node 1."""
        with patch.object(comfoconnect, "is_connected", return_value=True):
            with pytest.raises(VentilationUnitNotFoundException):
                await comfoconnect.get_speed()

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
    @pytest.mark.parametrize(
        "property_type,message,expected",
        [
            (PdoType.TYPE_CN_BOOL, b"\x02", True),
            (PdoType.TYPE_CN_BOOL, b"\x00", False),
            (PdoType.TYPE_CN_UINT8, b"\xff", 255),
            (PdoType.TYPE_CN_UINT16, b"\xff\xff", 65535),
            (PdoType.TYPE_CN_UINT32, b"\x00\x00\x00\x80", 2147483648),
            (PdoType.TYPE_CN_INT8, b"\x80", -128),
            (PdoType.TYPE_CN_INT16, b"\xec\xff", -20),
            (PdoType.TYPE_CN_INT64, b"\xff" * 8, -1),
            (PdoType.TYPE_CN_STRING, b"ComfoAir Q\x00\x00", "ComfoAir Q"),
            (PdoType.TYPE_CN_TIME, b"\x01\x02", b"\x01\x02"),
            (PdoType.TYPE_CN_VERSION, b"\x01\x02", b"\x01\x02"),
            (None, b"\x01\x02", b"\x01\x02"),
        ],
    )
    async def test_get_single_property_types(self, comfoconnect, property_type, message, expected):
        """Test that each property type is decoded like before, and other types return the raw bytes."""
        mock_response = Mock()
        mock_response.message = message

        with patch.object(comfoconnect, "cmd_rmi_request", AsyncMock(return_value=mock_response)):
            assert await comfoconnect.get_single_property(0x01, 0x01, 0x04, property_type) == expected

    @pytest.mark.asyncio
    @pytest.mark.parametrize("property_type", [PdoType.TYPE_CN_BOOL, PdoType.TYPE_CN_STRING, PdoType.TYPE_CN_TIME, PdoType.TYPE_CN_VERSION, None])
    async def test_get_property_constraints_rejects_non_numeric(self, comfoconnect, property_type):
        """Test that only numeric property types have a range."""
        from aiocomfoconnect.properties import Property

        with patch.object(comfoconnect, "cmd_rmi_request", AsyncMock()) as mock_rmi, pytest.raises(ValueError, match="has no range"):
            await comfoconnect.get_property_constraints(Property(0x01, 0x01, 0x04, property_type))
        mock_rmi.assert_not_called()

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

    @pytest.mark.asyncio
    async def test_get_property_on_comfoclime(self, comfoconnect):
        """A ComfoClime property is read from the ComfoClime node, without passing its node id."""
        node_notification(comfoconnect, node_id=1, product_id=ProductId.COMFOAIRQ)
        node_notification(comfoconnect, node_id=2, product_id=ProductId.COMFOCLIME)

        with patch.object(comfoconnect, "cmd_rmi_request", AsyncMock(return_value=Mock(message=b"\xd7\x00"))) as mock_rmi:
            assert await comfoconnect.get_property(PROPERTY_CLIME_HEATING_COMFORT_TEMP) == 215

            mock_rmi.assert_called_once_with(bytes([0x01, 0x16, 0x01, 0x10, 0x09]), node_id=2)

    @pytest.mark.asyncio
    async def test_set_property_on_comfoclime(self, comfoconnect):
        """A ComfoClime property is written to the ComfoClime node, without passing its node id."""
        node_notification(comfoconnect, node_id=1, product_id=ProductId.COMFOAIRQ)
        node_notification(comfoconnect, node_id=2, product_id=ProductId.COMFOCLIME)

        with patch.object(comfoconnect, "cmd_rmi_request", AsyncMock()) as mock_rmi:
            await comfoconnect.set_property(PROPERTY_CLIME_HEATING_COMFORT_TEMP, 215)

            mock_rmi.assert_called_once_with(bytes([0x03, 0x16, 0x01, 0x09, 0xD7, 0x00]), node_id=2)

    @pytest.mark.asyncio
    async def test_property_node_id_overrides_product(self, comfoconnect):
        """An explicit node id wins over the node of the property, e.g. to read the serial number of the ComfoClime."""
        node_notification(comfoconnect, node_id=1, product_id=ProductId.COMFOAIRQ)
        node_notification(comfoconnect, node_id=2, product_id=ProductId.COMFOCLIME)

        with patch.object(comfoconnect, "cmd_rmi_request", AsyncMock(return_value=Mock(message=b"\x01"))) as mock_rmi:
            await comfoconnect.get_property(PROPERTY_SERIAL_NUMBER, node_id=2)
            await comfoconnect.set_property(PROPERTY_TEMPERATURE_PROFILE_MODE, 1, node_id=5)
            await comfoconnect.set_property(PROPERTY_TEMPERATURE_PROFILE_MODE, 1, 6)

        assert [rmi_call.kwargs for rmi_call in mock_rmi.await_args_list] == [{"node_id": 2}, {"node_id": 5}, {"node_id": 6}]

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "call",
        [
            lambda ccb: ccb.get_property(PROPERTY_CLIME_SEASON),
            lambda ccb: ccb.set_property(PROPERTY_CLIME_SEASON, 1),
            lambda ccb: ccb.get_property_constraints(PROPERTY_CLIME_HEATING_COMFORT_TEMP),
        ],
    )
    async def test_property_on_missing_comfoclime(self, comfoconnect, call):
        """Addressing a ComfoClime property without a ComfoClime on the bus raises, and sends nothing."""
        node_notification(comfoconnect, node_id=1, product_id=ProductId.COMFOAIRQ)

        with patch.object(comfoconnect, "cmd_rmi_request", AsyncMock()) as mock_rmi:
            with pytest.raises(ComfoClimeNotFoundException):
                await call(comfoconnect)
            with pytest.raises(NodeNotFoundException):
                await call(comfoconnect)

            mock_rmi.assert_not_called()

    @pytest.mark.asyncio
    async def test_property_on_missing_node(self, comfoconnect):
        """A property of another product that isn't on the bus raises a NodeNotFoundException."""
        node_notification(comfoconnect, node_id=1, product_id=ProductId.COMFOAIRQ)

        with pytest.raises(NodeNotFoundException):
            await comfoconnect.get_property(Property(0x01, 0x01, 0x04, PdoType.TYPE_CN_STRING, product=ProductId.COMFOSENSE))

    def test_property_products(self):
        """The ComfoClime properties live on the ComfoClime, the others on the ventilation unit."""
        clime = {name for name in dir(properties) if name.startswith("PROPERTY_CLIME_")}
        others = {name for name in dir(properties) if name.startswith("PROPERTY_") and name not in clime}

        assert clime and others
        assert all(getattr(properties, name).product == ProductId.COMFOCLIME for name in clime)
        assert all(getattr(properties, name).product is None for name in others)


# The RMI requests that the high-level commands send. A schedule request (0x84) is the command, the unit, the subunit, the
# schedule item, four zero bytes, a signed 32-bit little-endian field with the timeout in seconds for the commands that take
# one (-1 is no timeout), and the value.
@pytest.mark.parametrize(
    "method, args, expected",
    [
        ("get_mode", (), ["83 15 08 01"]),
        ("set_mode", ("auto",), ["85 15 08 01", "85 15 01 01"]),
        ("set_mode", ("manual",), ["84 15 08 01 00000000 01000000 01"]),
        ("get_speed", (), ["83 15 01 01"]),
        ("set_speed", ("away",), ["84 15 01 01 00000000 01000000 00"]),
        ("set_speed", ("low",), ["84 15 01 01 00000000 01000000 01"]),
        ("set_speed", ("medium",), ["84 15 01 01 00000000 01000000 02"]),
        ("set_speed", ("high",), ["84 15 01 01 00000000 01000000 03"]),
        ("get_bypass", (), ["83 15 02 01"]),
        ("set_bypass", ("auto",), ["85 15 02 01"]),
        ("set_bypass", ("on",), ["84 15 02 01 00000000 ffffffff 01"]),
        ("set_bypass", ("off",), ["84 15 02 01 00000000 ffffffff 02"]),
        ("set_bypass", ("on", 3600), ["84 15 02 01 00000000 100e0000 01"]),
        ("get_balance_mode", (), ["83 15 06 01", "83 15 07 01"]),
        ("set_balance_mode", ("balance",), ["85 15 06 01", "85 15 07 01"]),
        ("set_balance_mode", ("supply_only",), ["84 15 06 01 00000000 ffffffff 01", "85 15 07 01"]),
        ("set_balance_mode", ("exhaust_only",), ["85 15 06 01", "84 15 07 01 00000000 ffffffff 01"]),
        ("set_balance_mode", ("supply_only", 600), ["84 15 06 01 00000000 58020000 01", "85 15 07 01"]),
        ("get_boost", (), ["83 15 01 06"]),
        ("set_boost", (True,), ["84 15 01 06 00000000 100e0000 03"]),
        ("set_boost", (True, 600), ["84 15 01 06 00000000 58020000 03"]),
        ("set_boost", (False,), ["85 15 01 06"]),
        ("get_away", (), ["83 15 01 0b"]),
        ("set_away", (True,), ["84 15 01 0b 00000000 100e0000 00"]),
        ("set_away", (True, -1), ["84 15 01 0b 00000000 ffffffff 00"]),
        ("set_away", (False,), ["85 15 01 0b"]),
        ("get_comfocool_mode", (), ["83 15 05 01"]),
        ("set_comfocool_mode", ("auto",), ["85 15 05 01"]),
        ("set_comfocool_mode", ("off",), ["84 15 05 01 00000000 ffffffff 00"]),
        ("set_comfocool_mode", ("off", 3600), ["84 15 05 01 00000000 100e0000 00"]),
        ("get_temperature_profile", (), ["83 15 03 01"]),
        ("set_temperature_profile", ("warm",), ["84 15 03 01 00000000 ffffffff 02"]),
        ("set_temperature_profile", ("normal",), ["84 15 03 01 00000000 ffffffff 00"]),
        ("set_temperature_profile", ("cool",), ["84 15 03 01 00000000 ffffffff 01"]),
        ("set_temperature_profile", ("warm", 3600), ["84 15 03 01 00000000 100e0000 02"]),
        ("get_sensor_ventmode_temperature_passive", (), ["01 1d 01 10 04"]),
        ("set_sensor_ventmode_temperature_passive", ("auto",), ["03 1d 01 04 01"]),
        ("set_sensor_ventmode_temperature_passive", ("on",), ["03 1d 01 04 02"]),
        ("set_sensor_ventmode_temperature_passive", ("off",), ["03 1d 01 04 00"]),
        ("get_sensor_ventmode_humidity_comfort", (), ["01 1d 01 10 06"]),
        ("set_sensor_ventmode_humidity_comfort", ("auto",), ["03 1d 01 06 01"]),
        ("set_sensor_ventmode_humidity_comfort", ("on",), ["03 1d 01 06 02"]),
        ("set_sensor_ventmode_humidity_comfort", ("off",), ["03 1d 01 06 00"]),
        ("get_sensor_ventmode_humidity_protection", (), ["01 1d 01 10 07"]),
        ("set_sensor_ventmode_humidity_protection", ("auto",), ["03 1d 01 07 01"]),
        ("set_sensor_ventmode_humidity_protection", ("on",), ["03 1d 01 07 02"]),
        ("set_sensor_ventmode_humidity_protection", ("off",), ["03 1d 01 07 00"]),
        ("clear_errors", (), ["82 03 01"]),
        ("get_property", (PROPERTY_TEMPERATURE_PROFILE_MODE,), ["01 1d 01 10 08"]),
        ("set_property", (PROPERTY_TEMPERATURE_PROFILE_MODE, 1), ["03 1d 01 08 01"]),
        ("set_property", (PROPERTY_RMOT_HEATING_THRESHOLD, -15), ["03 1d 01 02 f1ff"]),
        ("set_property_typed", (0x1D, 0x01, 0x02, -15, PdoType.TYPE_CN_INT16), ["03 1d 01 02 f1ff"]),
        ("get_timer", (0x02, 0x01), ["83 15 02 01"]),
        ("set_timer", (0x02, 0x01, 0x01), ["84 15 02 01 00000000 ffffffff 01"]),
        ("set_timer", (0x01, 0x06, 0x03, 600), ["84 15 01 06 00000000 58020000 03"]),
        ("cancel_timer", (0x02, 0x01), ["85 15 02 01"]),
    ],
)
async def test_command_rmi_bytes(method, args, expected):
    """Every high-level command sends exactly these RMI requests."""
    comfoconnect = ComfoConnect("127.0.0.1", LOCAL_UUID)

    def reply(request, node_id=None):  # pylint: disable=unused-argument
        # An active timer for the schedule "get timer" requests, a single byte for the rest.
        return Mock(message=bytes.fromhex("01 00000000 ffffffff ffffffff 01") if request[0] == 0x83 else b"\x01")

    with patch.object(comfoconnect, "cmd_rmi_request", AsyncMock(side_effect=reply)) as mock_rmi:
        await getattr(comfoconnect, method)(*args)

    assert [rmi_call.args for rmi_call in mock_rmi.await_args_list] == [(bytes.fromhex(request),) for request in expected]


# Replies to a schedule "get timer" request (0x83): active, delay, duration, remaining time and value. An inactive timer keeps
# the fields of its last run.
@pytest.mark.parametrize(
    "method, replies, expected",
    [
        ("get_mode", ["00 00000000 ffffffff 00000000 01"], "auto"),
        ("get_mode", ["01 00000000 ffffffff ffffffff 01"], "manual"),
        ("get_speed", ["01 00000000 ffffffff ffffffff 00"], "away"),
        ("get_speed", ["01 00000000 ffffffff ffffffff 03"], "high"),
        ("get_speed", ["00 00000000 ffffffff 00000000 03"], None),
        ("get_bypass", ["01 00000000 100e0000 0b0e0000 01"], "on"),
        ("get_bypass", ["01 00000000 100e0000 0d0e0000 02"], "off"),
        ("get_bypass", ["00 00000000 100e0000 00000000 01"], "auto"),
        ("get_balance_mode", ["00 00000000 08070000 00000000 01", "00 00000000 08070000 00000000 01"], "balance"),
        ("get_balance_mode", ["01 00000000 100e0000 0e0e0000 01", "00 00000000 08070000 00000000 01"], "supply_only"),
        ("get_balance_mode", ["00 00000000 08070000 00000000 01", "01 00000000 100e0000 0e0e0000 01"], "exhaust_only"),
        ("get_boost", ["01 00000000 58020000 56020000 03"], True),
        ("get_boost", ["00 00000000 58020000 00000000 03"], False),
        ("get_away", ["01 00000000 55020000 53020000 00"], True),
        ("get_away", ["00 00000000 b0040000 00000000 00"], False),
        ("get_comfocool_mode", ["01 00000000 ffffffff ffffffff 00"], "off"),
        ("get_comfocool_mode", ["00 00000000 ffffffff 00000000 00"], "auto"),
        ("get_temperature_profile", ["01 00000000 ffffffff ffffffff 02"], "warm"),
        ("get_temperature_profile", ["01 00000000 ffffffff ffffffff 00"], "normal"),
        ("get_temperature_profile", ["00 00000000 100e0000 00000000 01"], None),
    ],
)
async def test_timer_getters(method, replies, expected):
    """The timer getters only use the value of an active timer."""
    comfoconnect = ComfoConnect("127.0.0.1", LOCAL_UUID)
    with patch.object(comfoconnect, "cmd_rmi_request", AsyncMock(side_effect=[Mock(message=bytes.fromhex(reply)) for reply in replies])):
        assert await getattr(comfoconnect, method)() == expected


async def test_get_timer():
    """get_timer returns all the fields of the timer entry."""
    comfoconnect = ComfoConnect("127.0.0.1", LOCAL_UUID)
    with patch.object(comfoconnect, "cmd_rmi_request", AsyncMock(return_value=Mock(message=bytes.fromhex("01 00000000 58020000 56020000 03")))):
        assert await comfoconnect.get_timer(SCHEDULE_PRESET, TIMER_BOOST) == TimerEntry(active=True, delay=0, duration=600, remaining=598, value=3)


@pytest.mark.parametrize("method", ["get_speed", "get_bypass", "get_temperature_profile"])
async def test_timer_getters_reject_unknown_value(method):
    """A timer getter raises a ValueError for a value it doesn't know."""
    comfoconnect = ComfoConnect("127.0.0.1", LOCAL_UUID)
    with patch.object(comfoconnect, "cmd_rmi_request", AsyncMock(return_value=Mock(message=bytes.fromhex("01 00000000 ffffffff ffffffff 04")))):
        with pytest.raises(ValueError):
            await getattr(comfoconnect, method)()


@pytest.mark.parametrize("method", ["set_speed", "set_bypass", "set_temperature_profile"])
async def test_timer_setters_reject_unknown_value(method):
    """A timer setter raises a ValueError for a value it doesn't know, and sends nothing."""
    comfoconnect = ComfoConnect("127.0.0.1", LOCAL_UUID)
    with patch.object(comfoconnect, "cmd_rmi_request", AsyncMock()) as mock_rmi:
        with pytest.raises(ValueError):
            await getattr(comfoconnect, method)("turbo")

    mock_rmi.assert_not_called()
