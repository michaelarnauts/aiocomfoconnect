""" ComfoConnect Bridge API abstraction """

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Dict, List, Literal, Optional

from aiocomfoconnect import Bridge
from aiocomfoconnect.const import (
    ERRORS,
    ERRORS_140,
    SUBUNIT_01,
    SUBUNIT_02,
    SUBUNIT_03,
    SUBUNIT_05,
    SUBUNIT_06,
    SUBUNIT_07,
    SUBUNIT_08,
    UNIT_ERROR,
    UNIT_SCHEDULE,
    UNIT_TEMPHUMCONTROL,
    UNIT_VENTILATIONCONFIG,
    ComfoCoolMode,
    PdoType,
    VentilationBalance,
    VentilationMode,
    VentilationSetting,
    VentilationSpeed,
    VentilationTemperatureProfile,
)
from aiocomfoconnect.exceptions import (
    AioComfoConnectNotConnected,
    AioComfoConnectTimeout,
    ComfoConnectNotAllowed,
)
from aiocomfoconnect.properties import Property
from aiocomfoconnect.sensors import Sensor
from aiocomfoconnect.util import bytearray_to_bits, bytestring, encode_pdo_value

_LOGGER = logging.getLogger(__name__)


class ComfoConnect(Bridge):
    """Abstraction layer over the ComfoConnect LAN C API."""

    def __init__(self, host: str, uuid: str, loop=None, sensor_callback=None, alarm_callback=None, sensor_delay=2, connect_timeout=30):
        """Initialize the ComfoConnect class."""
        super().__init__(host, uuid, loop)

        self.set_sensor_callback(self._sensor_callback)  # Set the callback to our _sensor_callback method, so we can proces the callbacks.
        self.set_alarm_callback(self._alarm_callback)  # Set the callback to our _alarm_callback method, so we can proces the callbacks.
        self.sensor_delay = sensor_delay
        self.connect_timeout = connect_timeout

        self._sensor_callback_fn: Optional[Callable[[Sensor, Any], None]] = sensor_callback
        self._alarm_callback_fn: Optional[Callable[[int, Dict[int, str]], None]] = alarm_callback
        self._sensors: Dict[int, Sensor] = {}
        self._sensors_values: Dict[int, Any] = {}
        self._sensor_hold: Optional[asyncio.Handle] = None

        self._reconnect_task: Optional[asyncio.Task] = None
        self._is_stopping = False
        self._session_ready: Optional[asyncio.Future] = None

    def _unhold_sensors(self):
        """Unhold the sensors."""
        _LOGGER.debug("Unholding sensors")
        self._sensor_hold = None

        # Emit the current cached values of the sensors, by now, they should have received a correct update.
        for sensor_id, _ in self._sensors.items():
            if self._sensors_values.get(sensor_id) is not None:
                self._sensor_callback(sensor_id, self._sensors_values.get(sensor_id))

    async def connect(self, uuid: str):
        """Connect to the bridge with automatic reconnection."""
        if self._reconnect_task and not self._reconnect_task.done():
            _LOGGER.warning("Already connected or connecting")
            return

        # Get the running loop if not provided
        if self._loop is None:
            self._loop = asyncio.get_running_loop()

        self._is_stopping = False
        if self._session_ready and not self._session_ready.done():
            self._session_ready.cancel()
        self._session_ready = self._loop.create_future()
        self._reconnect_task = self._loop.create_task(self._reconnect_loop(uuid))

        try:
            await asyncio.wait_for(self._session_ready, timeout=self.connect_timeout)
        except asyncio.TimeoutError as exc:
            self._is_stopping = True
            if self._reconnect_task and not self._reconnect_task.done():
                self._reconnect_task.cancel()
                try:
                    await self._reconnect_task
                except asyncio.CancelledError:
                    pass
            if self._session_ready and not self._session_ready.done():
                self._session_ready.set_exception(AioComfoConnectTimeout(f"Failed to connect within {self.connect_timeout} seconds"))
            self._reconnect_task = None
            raise AioComfoConnectTimeout(f"Failed to connect within {self.connect_timeout} seconds") from exc
        except Exception:  # pylint: disable=broad-exception-caught
            self._is_stopping = True
            if self._reconnect_task and not self._reconnect_task.done():
                self._reconnect_task.cancel()
                try:
                    await self._reconnect_task
                except asyncio.CancelledError:
                    pass
            self._reconnect_task = None
            raise

    async def _reconnect_loop(self, uuid: str):
        """Reconnection loop that maintains connection to the bridge."""
        while not self._is_stopping:
            try:
                # Connect to the bridge
                await super().connect(uuid)
                _LOGGER.info("Connected to bridge %s", self.host)

                # Start session
                await self.cmd_start_session(True)

                # Wait for a specified amount of seconds to buffer sensor values.
                # This is to work around a bug where the bridge sends invalid sensor values when connecting.
                if self.sensor_delay:
                    _LOGGER.debug("Holding sensors for %s second(s)", self.sensor_delay)
                    self._sensors_values = {}
                    self._sensor_hold = self._loop.call_later(self.sensor_delay, self._unhold_sensors)

                # Register the sensors again (in case we lost the connection)
                for sensor in self._sensors.values():
                    await self.cmd_rpdo_request(sensor.id, sensor.type)

                if self._session_ready and not self._session_ready.done():
                    self._session_ready.set_result(True)

                # Wait for the read task to finish (it will raise an exception on disconnect)
                await self._read_task

            except asyncio.CancelledError:
                _LOGGER.debug("Reconnect loop cancelled")
                break

            except ComfoConnectNotAllowed as exc:
                _LOGGER.error("Not allowed to connect (not registered?): %s", exc)
                if self._session_ready and not self._session_ready.done():
                    self._session_ready.set_exception(exc)
                break

            except AioComfoConnectTimeout:
                _LOGGER.warning("Connection timeout, retrying in 5 seconds...")
                await asyncio.sleep(5)

            except AioComfoConnectNotConnected:
                _LOGGER.info("Disconnected from bridge, reconnecting...")
                await asyncio.sleep(1)

            except Exception as exc:  # pylint: disable=broad-exception-caught
                _LOGGER.error("Unexpected error in reconnect loop: %s", exc, exc_info=True)
                await asyncio.sleep(5)

            finally:
                # Ensure we're properly disconnected before reconnecting
                if self.is_connected():
                    await super().disconnect()

        _LOGGER.info("Reconnect loop stopped")
        if self._session_ready and not self._session_ready.done():
            self._session_ready.set_exception(AioComfoConnectNotConnected("Reconnect loop stopped"))

    async def disconnect(self):
        """Disconnect from the bridge and stop reconnection."""
        _LOGGER.debug("Stopping reconnection and disconnecting")
        self._is_stopping = True

        # Cancel sensor hold timer
        if self._sensor_hold:
            self._sensor_hold.cancel()
            self._sensor_hold = None

        # Stop reconnection loop
        if self._reconnect_task and not self._reconnect_task.done():
            self._reconnect_task.cancel()
            try:
                await self._reconnect_task
            except asyncio.CancelledError:
                pass

        # Disconnect from bridge
        await super().disconnect()
        self._reconnect_task = None
        self._session_ready = None

    async def register_sensor(self, sensor: Sensor):
        """Register a sensor on the bridge."""
        self._sensors[sensor.id] = sensor
        self._sensors_values[sensor.id] = None
        await self.cmd_rpdo_request(sensor.id, sensor.type)

    async def deregister_sensor(self, sensor: Sensor):
        """Deregister a sensor on the bridge."""
        await self.cmd_rpdo_request(sensor.id, sensor.type, timeout=0)
        del self._sensors[sensor.id]
        del self._sensors_values[sensor.id]

    async def get_property(self, prop: Property, node_id=1) -> Any:
        """Get a property and convert to the right type."""
        return await self.get_single_property(prop.unit, prop.subunit, prop.property_id, prop.property_type, node_id=node_id)

    async def get_single_property(self, unit: int, subunit: int, property_id: int, property_type: int = None, node_id=1) -> Any:
        """Get a property and convert to the right type."""
        result = await self.cmd_rmi_request(bytes([0x01, unit, subunit, 0x10, property_id]), node_id=node_id)

        if property_type == PdoType.TYPE_CN_STRING:
            return result.message.decode("utf-8").rstrip("\x00")
        if property_type in [PdoType.TYPE_CN_INT8, PdoType.TYPE_CN_INT16, PdoType.TYPE_CN_INT64]:
            return int.from_bytes(result.message, byteorder="little", signed=True)
        if property_type in [PdoType.TYPE_CN_UINT8, PdoType.TYPE_CN_UINT16, PdoType.TYPE_CN_UINT32]:
            return int.from_bytes(result.message, byteorder="little", signed=False)
        if property_type == PdoType.TYPE_CN_BOOL:
            return bool(result.message[0])

        return result.message

    async def get_multiple_properties(self, unit: int, subunit: int, property_ids: List[int], node_id=1) -> Any:
        """Get multiple properties."""
        result = await self.cmd_rmi_request(bytestring([0x02, unit, subunit, 0x01, 0x10 | len(property_ids), bytes(property_ids)]), node_id=node_id)

        return result.message

    async def set_property(self, unit: int, subunit: int, property_id: int, value: int, node_id=1) -> Any:
        """Set a property."""
        result = await self.cmd_rmi_request(bytes([0x03, unit, subunit, property_id, value]), node_id=node_id)

        return result.message

    async def set_property_typed(self, unit: int, subunit: int, property_id: int, value: int, pdo_type: PdoType, node_id=1) -> Any:
        """Set a typed property."""
        value_bytes = encode_pdo_value(value, pdo_type)
        message_bytes = bytes([0x03, unit, subunit, property_id]) + value_bytes

        result = await self.cmd_rmi_request(message_bytes, node_id=node_id)

        return result.message

    def _sensor_callback(self, sensor_id, sensor_value):
        """Callback function for sensor updates."""
        if self._sensor_callback_fn is None:
            return

        sensor = self._sensors.get(sensor_id)
        if sensor is None:
            _LOGGER.error("Unknown sensor id: %s", sensor_id)
            return

        self._sensors_values[sensor_id] = sensor_value

        # Don't emit sensor values until we have received all the initial values.
        if self._sensor_hold is not None:
            return

        if sensor.value_fn:
            val = sensor.value_fn(sensor_value)
        else:
            val = round(sensor_value, 2)
        self._sensor_callback_fn(sensor, val)

    def _alarm_callback(self, node_id, alarm):
        """Callback function for alarm updates."""
        if self._alarm_callback_fn is None:
            return

        if alarm.swProgramVersion <= 3222278144:
            # Firmware 1.4.0 and below
            error_messages = ERRORS_140
        else:
            error_messages = ERRORS

        errors = {bit: error_messages[bit] for bit in bytearray_to_bits(alarm.errors)}
        self._alarm_callback_fn(node_id, errors)

    async def get_mode(self):
        """Get the current mode."""
        result = await self.cmd_rmi_request(bytes([0x83, UNIT_SCHEDULE, SUBUNIT_08, 0x01]))
        # 0000000000ffffffff0000000001 = auto
        # 0100000000ffffffffffffffff01 = manual
        mode = result.message[0]

        return VentilationMode.MANUAL if mode == 1 else VentilationMode.AUTO

    async def set_mode(self, mode: Literal["auto", "manual"]):
        """Set the ventilation mode (auto / manual)."""
        if mode == VentilationMode.AUTO:
            await self.cmd_rmi_request(bytes([0x85, UNIT_SCHEDULE, SUBUNIT_08, 0x01]))
        elif mode == VentilationMode.MANUAL:
            await self.cmd_rmi_request(bytes([0x84, UNIT_SCHEDULE, SUBUNIT_08, 0x01, 0x00, 0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x01]))
        else:
            raise ValueError(f"Invalid mode: {mode}")

    async def get_speed(self):
        """Set the ventilation speed (away / low / medium / high)."""
        result = await self.cmd_rmi_request(bytes([0x83, UNIT_SCHEDULE, SUBUNIT_01, 0x01]))
        # 0100000000ffffffffffffffff00 = away
        # 0100000000ffffffffffffffff01 = low
        # 0100000000ffffffffffffffff02 = medium
        # 0100000000ffffffffffffffff03 = high
        speed = result.message[-1]

        if speed == 0:
            return VentilationSpeed.AWAY
        if speed == 1:
            return VentilationSpeed.LOW
        if speed == 2:
            return VentilationSpeed.MEDIUM
        if speed == 3:
            return VentilationSpeed.HIGH

        raise ValueError(f"Invalid speed: {speed}")

    async def set_speed(self, speed: Literal["away", "low", "medium", "high"]):
        """Get the ventilation speed (away / low / medium / high)."""
        if speed == VentilationSpeed.AWAY:
            await self.cmd_rmi_request(bytes([0x84, UNIT_SCHEDULE, SUBUNIT_01, 0x01, 0x00, 0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00]))
        elif speed == VentilationSpeed.LOW:
            await self.cmd_rmi_request(bytes([0x84, UNIT_SCHEDULE, SUBUNIT_01, 0x01, 0x00, 0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x01]))
        elif speed == VentilationSpeed.MEDIUM:
            await self.cmd_rmi_request(bytes([0x84, UNIT_SCHEDULE, SUBUNIT_01, 0x01, 0x00, 0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x02]))
        elif speed == VentilationSpeed.HIGH:
            await self.cmd_rmi_request(bytes([0x84, UNIT_SCHEDULE, SUBUNIT_01, 0x01, 0x00, 0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x03]))
        else:
            raise ValueError(f"Invalid speed: {speed}")

    async def get_flow_for_speed(self, speed: Literal["away", "low", "medium", "high"]) -> int:
        """Get the targeted airflow in m³/h for the given VentilationSpeed (away / low / medium / high)."""

        match speed:
            case VentilationSpeed.AWAY:
                property_id = 3
            case VentilationSpeed.LOW:
                property_id = 4
            case VentilationSpeed.MEDIUM:
                property_id = 5
            case VentilationSpeed.HIGH:
                property_id = 6

        return await self.get_single_property(UNIT_VENTILATIONCONFIG, SUBUNIT_01, property_id, PdoType.TYPE_CN_INT16)

    async def set_flow_for_speed(self, speed: Literal["away", "low", "medium", "high"], desired_flow: int):
        """Set the targeted airflow in m³/h for the given VentilationSpeed (away / low / medium / high)."""

        match speed:
            case VentilationSpeed.AWAY:
                property_id = 3
            case VentilationSpeed.LOW:
                property_id = 4
            case VentilationSpeed.MEDIUM:
                property_id = 5
            case VentilationSpeed.HIGH:
                property_id = 6

        await self.set_property_typed(UNIT_VENTILATIONCONFIG, SUBUNIT_01, property_id, desired_flow, PdoType.TYPE_CN_INT16)

    async def get_bypass(self):
        """Get the bypass mode (auto / on / off)."""
        result = await self.cmd_rmi_request(bytes([0x83, UNIT_SCHEDULE, SUBUNIT_02, 0x01]))
        # 0000000000080700000000000000 = auto
        # 0100000000100e00000b0e000001 = open
        # 0100000000100e00000d0e000002 = close
        mode = result.message[-1]

        if mode == 0:
            return VentilationSetting.AUTO
        if mode == 1:
            return VentilationSetting.ON
        if mode == 2:
            return VentilationSetting.OFF

        raise ValueError(f"Invalid mode: {mode}")

    async def set_bypass(self, mode: Literal["auto", "on", "off"], timeout=-1):
        """Set the bypass mode (auto / on / off)."""
        if mode == VentilationSetting.AUTO:
            await self.cmd_rmi_request(bytes([0x85, UNIT_SCHEDULE, SUBUNIT_02, 0x01]))
        elif mode == VentilationSetting.ON:
            await self.cmd_rmi_request(bytestring([0x84, UNIT_SCHEDULE, SUBUNIT_02, 0x01, 0x00, 0x00, 0x00, 0x00, timeout.to_bytes(4, "little", signed=True), 0x01]))
        elif mode == VentilationSetting.OFF:
            await self.cmd_rmi_request(bytestring([0x84, UNIT_SCHEDULE, SUBUNIT_02, 0x01, 0x00, 0x00, 0x00, 0x00, timeout.to_bytes(4, "little", signed=True), 0x02]))
        else:
            raise ValueError(f"Invalid mode: {mode}")

    async def get_balance_mode(self):
        """Get the ventilation balance mode (balance / supply only / exhaust only)."""
        result_06 = await self.cmd_rmi_request(bytes([0x83, UNIT_SCHEDULE, SUBUNIT_06, 0x01]))
        result_07 = await self.cmd_rmi_request(bytes([0x83, UNIT_SCHEDULE, SUBUNIT_07, 0x01]))
        # result_06:
        # 0000000000080700000000000001 = balance
        # 0100000000100e00000e0e000001 = supply only
        # 0000000000080700000000000001 = exhaust only

        # result_07:
        # 0000000000080700000000000001 = balance
        # 0000000000080700000000000001 = supply only
        # 0100000000100e00000e0e000001 = exhaust only
        mode_06 = result_06.message[0]
        mode_07 = result_07.message[0]

        if mode_06 == mode_07:
            return VentilationBalance.BALANCE
        if mode_06 == 1 and mode_07 == 0:
            return VentilationBalance.SUPPLY_ONLY
        if mode_06 == 0 and mode_07 == 1:
            return VentilationBalance.EXHAUST_ONLY

        raise ValueError(f"Invalid mode: 6={mode_06}, 7={mode_07}")

    async def set_balance_mode(self, mode: Literal["balance", "supply_only", "exhaust_only"], timeout=-1):
        """Set the ventilation balance mode (balance / supply only / exhaust only)."""
        if mode == VentilationBalance.BALANCE:
            await self.cmd_rmi_request(bytes([0x85, UNIT_SCHEDULE, SUBUNIT_06, 0x01]))
            await self.cmd_rmi_request(bytes([0x85, UNIT_SCHEDULE, SUBUNIT_07, 0x01]))
        elif mode == VentilationBalance.SUPPLY_ONLY:
            await self.cmd_rmi_request(bytestring([0x84, UNIT_SCHEDULE, SUBUNIT_06, 0x01, 0x00, 0x00, 0x00, 0x00, timeout.to_bytes(4, "little", signed=True), 0x01]))
            await self.cmd_rmi_request(bytes([0x85, UNIT_SCHEDULE, SUBUNIT_07, 0x01]))
        elif mode == VentilationBalance.EXHAUST_ONLY:
            await self.cmd_rmi_request(bytes([0x85, UNIT_SCHEDULE, SUBUNIT_06, 0x01]))
            await self.cmd_rmi_request(bytestring([0x84, UNIT_SCHEDULE, SUBUNIT_07, 0x01, 0x00, 0x00, 0x00, 0x00, timeout.to_bytes(4, "little", signed=True), 0x01]))
        else:
            raise ValueError(f"Invalid mode: {mode}")

    async def get_boost(self):
        """Get boost mode."""
        result = await self.cmd_rmi_request(bytes([0x83, UNIT_SCHEDULE, SUBUNIT_01, 0x06]))
        # 0000000000580200000000000003 = not active
        # 0100000000580200005602000003 = active
        mode = result.message[0]

        return mode == 1

    async def set_boost(self, mode: bool, timeout=3600):
        """Activate boost mode."""
        if mode:
            await self.cmd_rmi_request(bytestring([0x84, UNIT_SCHEDULE, SUBUNIT_01, 0x06, 0x00, 0x00, 0x00, 0x00, timeout.to_bytes(4, "little", signed=True), 0x03]))
        else:
            await self.cmd_rmi_request(bytes([0x85, UNIT_SCHEDULE, SUBUNIT_01, 0x06]))

    async def get_away(self):
        """Get away mode."""
        result = await self.cmd_rmi_request(bytes([0x83, UNIT_SCHEDULE, SUBUNIT_01, 0x0B]))
        # 0000000000b00400000000000000 = not active
        # 0100000000550200005302000000 = active
        mode = result.message[0]

        return mode == 1

    async def set_away(self, mode: bool, timeout=3600):
        """Activate away mode."""
        if mode:
            await self.cmd_rmi_request(bytestring([0x84, UNIT_SCHEDULE, SUBUNIT_01, 0x0B, 0x00, 0x00, 0x00, 0x00, timeout.to_bytes(4, "little", signed=True), 0x00]))
        else:
            await self.cmd_rmi_request(bytes([0x85, UNIT_SCHEDULE, SUBUNIT_01, 0x0B]))

    async def get_comfocool_mode(self):
        """Get the current comfocool mode."""
        result = await self.cmd_rmi_request(bytes([0x83, UNIT_SCHEDULE, SUBUNIT_05, 0x01]))
        mode = result.message[0]
        return mode == 0

    async def set_comfocool_mode(self, mode: Literal["auto", "off"], timeout=-1):
        """Set the comfocool mode (auto / off)."""
        if mode == ComfoCoolMode.AUTO:
            await self.cmd_rmi_request(bytes([0x85, UNIT_SCHEDULE, SUBUNIT_05, 0x01]))
        elif mode == ComfoCoolMode.OFF:
            await self.cmd_rmi_request(bytestring([0x84, UNIT_SCHEDULE, SUBUNIT_05, 0x01, 0x00, 0x00, 0x00, 0x00, timeout.to_bytes(4, "little", signed=True), 0x00]))

    async def get_temperature_profile(self):
        """Get the temperature profile (warm / normal / cool)."""
        result = await self.cmd_rmi_request(bytes([0x83, UNIT_SCHEDULE, SUBUNIT_03, 0x01]))
        # 0100000000ffffffffffffffff02 = warm
        # 0100000000ffffffffffffffff00 = normal
        # 0100000000ffffffffffffffff01 = cool
        mode = result.message[-1]

        if mode == 2:
            return VentilationTemperatureProfile.WARM
        if mode == 0:
            return VentilationTemperatureProfile.NORMAL
        if mode == 1:
            return VentilationTemperatureProfile.COOL

        raise ValueError(f"Invalid mode: {mode}")

    async def set_temperature_profile(self, profile: Literal["warm", "normal", "cool"], timeout=-1):
        """Set the temperature profile (warm / normal / cool)."""
        if profile == VentilationTemperatureProfile.WARM:
            await self.cmd_rmi_request(bytestring([0x84, UNIT_SCHEDULE, SUBUNIT_03, 0x01, 0x00, 0x00, 0x00, 0x00, timeout.to_bytes(4, "little", signed=True), 0x02]))
        elif profile == VentilationTemperatureProfile.NORMAL:
            await self.cmd_rmi_request(bytestring([0x84, UNIT_SCHEDULE, SUBUNIT_03, 0x01, 0x00, 0x00, 0x00, 0x00, timeout.to_bytes(4, "little", signed=True), 0x00]))
        elif profile == VentilationTemperatureProfile.COOL:
            await self.cmd_rmi_request(bytestring([0x84, UNIT_SCHEDULE, SUBUNIT_03, 0x01, 0x00, 0x00, 0x00, 0x00, timeout.to_bytes(4, "little", signed=True), 0x01]))
        else:
            raise ValueError(f"Invalid profile: {profile}")

    async def get_sensor_ventmode_temperature_passive(self):
        """Get sensor based ventilation mode - temperature passive (auto / on / off)."""
        result = await self.cmd_rmi_request(bytes([0x01, UNIT_TEMPHUMCONTROL, SUBUNIT_01, 0x10, 0x04]))
        # 00 = off
        # 01 = auto
        # 02 = on
        mode = int.from_bytes(result.message, "little")

        if mode == 1:
            return VentilationSetting.AUTO
        if mode == 2:
            return VentilationSetting.ON
        if mode == 0:
            return VentilationSetting.OFF

        raise ValueError(f"Invalid mode: {mode}")

    async def set_sensor_ventmode_temperature_passive(self, mode: Literal["auto", "on", "off"]):
        """Configure sensor based ventilation mode - temperature passive (auto / on / off)."""
        if mode == VentilationSetting.AUTO:
            await self.cmd_rmi_request(bytes([0x03, UNIT_TEMPHUMCONTROL, SUBUNIT_01, 0x04, 0x01]))
        elif mode == VentilationSetting.ON:
            await self.cmd_rmi_request(bytes([0x03, UNIT_TEMPHUMCONTROL, SUBUNIT_01, 0x04, 0x02]))
        elif mode == VentilationSetting.OFF:
            await self.cmd_rmi_request(bytes([0x03, UNIT_TEMPHUMCONTROL, SUBUNIT_01, 0x04, 0x00]))
        else:
            raise ValueError(f"Invalid mode: {mode}")

    async def get_sensor_ventmode_humidity_comfort(self):
        """Get sensor based ventilation mode - humidity comfort (auto / on / off)."""
        result = await self.cmd_rmi_request(bytes([0x01, UNIT_TEMPHUMCONTROL, SUBUNIT_01, 0x10, 0x06]))
        # 00 = off
        # 01 = auto
        # 02 = on
        mode = int.from_bytes(result.message, "little")

        if mode == 1:
            return VentilationSetting.AUTO
        if mode == 2:
            return VentilationSetting.ON
        if mode == 0:
            return VentilationSetting.OFF

        raise ValueError(f"Invalid mode: {mode}")

    async def set_sensor_ventmode_humidity_comfort(self, mode: Literal["auto", "on", "off"]):
        """Configure sensor based ventilation mode - humidity comfort (auto / on / off)."""
        if mode == VentilationSetting.AUTO:
            await self.cmd_rmi_request(bytes([0x03, UNIT_TEMPHUMCONTROL, SUBUNIT_01, 0x06, 0x01]))
        elif mode == VentilationSetting.ON:
            await self.cmd_rmi_request(bytes([0x03, UNIT_TEMPHUMCONTROL, SUBUNIT_01, 0x06, 0x02]))
        elif mode == VentilationSetting.OFF:
            await self.cmd_rmi_request(bytes([0x03, UNIT_TEMPHUMCONTROL, SUBUNIT_01, 0x06, 0x00]))
        else:
            raise ValueError(f"Invalid mode: {mode}")

    async def get_sensor_ventmode_humidity_protection(self):
        """Get sensor based ventilation mode - humidity protection (auto / on / off)."""
        result = await self.cmd_rmi_request(bytes([0x01, UNIT_TEMPHUMCONTROL, SUBUNIT_01, 0x10, 0x07]))
        # 00 = off
        # 01 = auto
        # 02 = on
        mode = int.from_bytes(result.message, "little")

        if mode == 1:
            return VentilationSetting.AUTO
        if mode == 2:
            return VentilationSetting.ON
        if mode == 0:
            return VentilationSetting.OFF

        raise ValueError(f"Invalid mode: {mode}")

    async def set_sensor_ventmode_humidity_protection(self, mode: Literal["auto", "on", "off"]):
        """Configure sensor based ventilation mode - humidity protection (auto / on / off)."""
        if mode == VentilationSetting.AUTO:
            await self.cmd_rmi_request(bytes([0x03, UNIT_TEMPHUMCONTROL, SUBUNIT_01, 0x07, 0x01]))
        elif mode == VentilationSetting.ON:
            await self.cmd_rmi_request(bytes([0x03, UNIT_TEMPHUMCONTROL, SUBUNIT_01, 0x07, 0x02]))
        elif mode == VentilationSetting.OFF:
            await self.cmd_rmi_request(bytes([0x03, UNIT_TEMPHUMCONTROL, SUBUNIT_01, 0x07, 0x00]))
        else:
            raise ValueError(f"Invalid mode: {mode}")

    async def clear_errors(self):
        """Clear the errors."""
        await self.cmd_rmi_request(bytes([0x82, UNIT_ERROR, 0x01]))
