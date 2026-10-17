"""Tests for the ComfoConnect class."""

from unittest.mock import AsyncMock, Mock, call, patch

import pytest

from aiocomfoconnect.comfoconnect import ComfoConnect
from aiocomfoconnect.const import ERRORS_BASE, ProductId
from aiocomfoconnect.exceptions import (
    AioComfoConnectNotConnected,
    ComfoClimeNotFoundException,
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

