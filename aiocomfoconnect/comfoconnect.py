""" ComfoConnect Bridge API abstraction """

from __future__ import annotations

import asyncio
import logging
import struct
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Literal, Optional

from aiocomfoconnect import Bridge
from aiocomfoconnect.const import (
    ERRORS,
    ERRORS_140,
    SUBUNIT_01,
    SUBUNIT_03,
    SUBUNIT_06,
    SUBUNIT_07,
    UNIT_ERROR,
    UNIT_SCHEDULE,
    UNIT_TEMPHUMCONTROL,
    UNIT_VENTILATIONCONFIG,
    ComfoCoolMode,
    ConnectionState,
    PdoType,
    SCHEDULE_BYPASS,
    SCHEDULE_COMFOCOOL,
    SCHEDULE_EXHAUST_ONLY,
    SCHEDULE_MANUAL_MODE,
    SCHEDULE_PRESET,
    SCHEDULE_SUPPLY_ONLY,
    SCHEDULE_TEMPERATURE_PROFILE,
    TIMER_AWAY,
    TIMER_BOOST,
    TIMER_DEFAULT,
    VentilationBalance,
    VentilationMode,
    VentilationSetting,
    VentilationSpeed,
    VentilationTemperatureProfile,
)
from aiocomfoconnect.exceptions import (
    AioComfoConnectNotConnected,
    AioComfoConnectTimeout,
    ComfoClimeNotFoundException,
    ComfoConnectError,
    ComfoConnectNotAllowed,
)
from aiocomfoconnect.properties import Property, PropertyConstraints
from aiocomfoconnect.sensors import Sensor
from aiocomfoconnect.util import bytearray_to_bits, bytestring, encode_pdo_value

_LOGGER = logging.getLogger(__name__)

# How long the reconnect loop waits before it connects again after the connection was lost, and after a failed attempt.
RECONNECT_DELAY = 1
RECONNECT_RETRY_DELAY = 5

# The size in bytes and the signedness of the numeric property types.
NUMERIC_PROPERTY_TYPES = {
    PdoType.TYPE_CN_UINT8: (1, False),
    PdoType.TYPE_CN_UINT16: (2, False),
    PdoType.TYPE_CN_UINT32: (4, False),
    PdoType.TYPE_CN_INT8: (1, True),
    PdoType.TYPE_CN_INT16: (2, True),
    PdoType.TYPE_CN_INT64: (8, True),
}


@dataclass
class TimerEntry:
    """A timer of the SCHEDULE unit, that overrides a setting with a value for a while."""

    active: bool
    delay: int  # Seconds before the timer starts.
    duration: int  # Seconds the timer runs, -1 is until it is cancelled.
    remaining: int  # Seconds left, -1 is until it is cancelled.
    value: int


class ComfoConnect(Bridge):
    """Abstraction layer over the ComfoConnect LAN C API."""

    def __init__(
        self,
        host: str,
        uuid: str,
        loop=None,
        sensor_callback=None,
        alarm_callback=None,
        sensor_delay=5,
        connect_timeout=30,
        bridge_type: int = 0,
        heartbeat_interval: Optional[float] = None,
        connection_state_callback: Optional[Callable[[str], None]] = None,
    ):
        """Initialize the ComfoConnect class.

        With a heartbeat_interval, we ask the bridge for its time when we received nothing for that many seconds, and
        reconnect when it doesn't answer. This detects a bridge that stopped answering without closing the connection.

        The connection_state_callback is called with a ConnectionState when the state of the session changes.
        """
        super().__init__(host, uuid, loop, bridge_type)

        self.set_sensor_callback(self._sensor_callback)  # Set the callback to our _sensor_callback method, so we can proces the callbacks.
        self.set_alarm_callback(self._alarm_callback)  # Set the callback to our _alarm_callback method, so we can proces the callbacks.
        self.sensor_delay = sensor_delay
        self.connect_timeout = connect_timeout
        self.heartbeat_interval = heartbeat_interval

        self._sensor_callback_fn: Optional[Callable[[Sensor, Any], None]] = sensor_callback
        self._alarm_callback_fn: Optional[Callable[[int, Dict[int, str]], None]] = alarm_callback
        self._connection_state_callback_fn: Optional[Callable[[str], None]] = connection_state_callback
        self._connection_state = ConnectionState.DISCONNECTED
        self._sensors: Dict[int, Sensor] = {}
        self._sensors_values: Dict[int, Any] = {}
        self._sensor_holds: Dict[int, asyncio.Handle] = {}

        self._reconnect_task: Optional[asyncio.Task] = None
        self._connect_lock = asyncio.Lock()

    def _hold_sensor(self, sensor_id: int):
        """Hold a sensor, so we don't emit the invalid values that the bridge sends when we subscribe to it."""
        if not self.sensor_delay or self._loop is None:
            return

        # Restart the hold if the sensor is already held.
        handle = self._sensor_holds.pop(sensor_id, None)
        if handle is not None:
            handle.cancel()

        _LOGGER.debug("Holding sensor %s for %s second(s)", sensor_id, self.sensor_delay)
        self._sensors_values[sensor_id] = None
        self._sensor_holds[sensor_id] = self._loop.call_later(self.sensor_delay, self._unhold_sensor, sensor_id)

    def _unhold_sensor(self, sensor_id: int):
        """Unhold a sensor."""
        _LOGGER.debug("Unholding sensor %s", sensor_id)
        self._sensor_holds.pop(sensor_id, None)

        # Emit the current cached value of the sensor, by now, it should have received a correct update.
        if self._sensors_values.get(sensor_id) is not None:
            self._sensor_callback(sensor_id, self._sensors_values.get(sensor_id))

    def _cancel_sensor_holds(self):
        """Cancel all pending sensor holds."""
        for handle in self._sensor_holds.values():
            handle.cancel()
        self._sensor_holds.clear()

    async def connect(self, uuid: str):
        """Connect to the bridge and start a session. Once connected, reconnect automatically when the connection is lost.

        Makes one attempt and raises its error, e.g. AioComfoConnectNotReachable or ComfoConnectNotAllowed, or
        AioComfoConnectTimeout after connect_timeout seconds. A connect() while another one is busy waits for it.
        """
        async with self._connect_lock:
            if self._reconnect_task is not None and not self._reconnect_task.done():
                _LOGGER.warning("Already connected or connecting")
                return

            try:
                async with asyncio.timeout(self.connect_timeout):
                    await self._start_session(uuid)
            except BaseException as exc:
                # Don't leave a connection behind, also not when we are cancelled.
                await super().disconnect()
                if isinstance(exc, TimeoutError):
                    raise AioComfoConnectTimeout(f"Failed to connect within {self.connect_timeout} seconds") from exc
                raise

            self._set_connection_state(ConnectionState.CONNECTED)
            self._reconnect_task = asyncio.create_task(self._reconnect_loop(uuid))

    async def _start_session(self, uuid: str):
        """Connect to the bridge, start a session and subscribe to the sensors."""
        await super().connect(uuid)
        _LOGGER.info("Connected to bridge %s", self.host)

        await self.cmd_start_session(True)

        # The bridge announces its nodes right after the session starts, but ask again
        # so we don't depend on that. Wait for the ventilation unit before we allow any
        # RMI commands, since it isn't always node 1 on newer firmware.
        await self.cmd_node_request()
        _LOGGER.info("Using node %s for the ventilation unit", await self.wait_for_ventilation_node())

        # Hold the sensor values for a specified amount of seconds.
        # This is to work around a bug where the bridge sends invalid sensor values when connecting.
        for sensor_id in self._sensors:
            self._hold_sensor(sensor_id)

        # Register the sensors again (in case we lost the connection). Iterate over a copy, since
        # register_sensor can be called while we wait. A sensor that fails shouldn't block the session.
        for sensor in list(self._sensors.values()):
            try:
                await self.cmd_rpdo_request(sensor.id, sensor.type)
            except (ComfoConnectError, AioComfoConnectTimeout) as exc:
                _LOGGER.warning("Failed to subscribe to sensor %s (%s): %r", sensor.id, sensor.name, exc)

    async def _reconnect_loop(self, uuid: str):
        """Start a new session every time the connection is lost, until disconnect() cancels us."""
        try:
            while True:
                await self._wait_for_disconnect()
                _LOGGER.info("Disconnected from bridge, reconnecting...")
                self._set_connection_state(ConnectionState.DISCONNECTED)
                delay = RECONNECT_DELAY
                while True:
                    # Clean up the connection before reconnecting, also when it already ended by itself.
                    await super().disconnect()
                    await asyncio.sleep(delay)
                    try:
                        await self._start_session(uuid)
                        self._set_connection_state(ConnectionState.CONNECTED)
                        break
                    except ComfoConnectNotAllowed as exc:
                        _LOGGER.error("Not allowed to connect (not registered?): %s", exc)
                        self._set_connection_state(ConnectionState.NOT_ALLOWED)
                        return
                    except Exception as exc:  # pylint: disable=broad-exception-caught
                        _LOGGER.warning("Could not reconnect: %r. Retrying in %s seconds...", exc, RECONNECT_RETRY_DELAY)
                        delay = RECONNECT_RETRY_DELAY
        finally:
            await super().disconnect()
            _LOGGER.info("Reconnect loop stopped")

    async def _wait_for_disconnect(self):
        """Wait until the connection is lost, or until the bridge doesn't answer the heartbeat."""
        # The read task ends when the connection is lost. It has already logged why.
        while not self._read_task.done():
            idle = time.monotonic() - self._last_received
            if self.heartbeat_interval is None or idle < self.heartbeat_interval:
                timeout = None if self.heartbeat_interval is None else self.heartbeat_interval - idle
                await asyncio.wait([self._read_task], timeout=timeout)
                continue

            try:
                await self.cmd_time_request()
            except ComfoConnectError:
                pass  # The bridge answered.
            except (AioComfoConnectTimeout, AioComfoConnectNotConnected):
                _LOGGER.warning("The bridge did not answer the heartbeat")
                return

    @property
    def connection_state(self) -> str:
        """The state of the session, one of ConnectionState. Unlike is_connected(), this is only CONNECTED once the session is up."""
        return self._connection_state

    def _set_connection_state(self, state: str):
        """Remember the state of the session, and tell the callback when it changed."""
        if state == self._connection_state:
            return
        self._connection_state = state
        if self._connection_state_callback_fn is None:
            return
        try:
            self._connection_state_callback_fn(state)
        except Exception:  # pylint: disable=broad-exception-caught
            _LOGGER.exception("Error in the connection state callback")

    async def disconnect(self):
        """Disconnect from the bridge and stop reconnecting. A connect() that is still busy fails."""
        _LOGGER.debug("Stopping reconnection and disconnecting")
        self._cancel_sensor_holds()

        # Close the connection of a connect() that is still busy, so it fails now instead of when it times out.
        if self._connect_lock.locked():
            await super().disconnect()

        async with self._connect_lock:
            if self._reconnect_task is not None:
                # The reconnect loop closes the connection when it stops.
                self._reconnect_task.cancel()
                await asyncio.wait([self._reconnect_task])
                self._reconnect_task = None
            await super().disconnect()
            self._set_connection_state(ConnectionState.DISCONNECTED)

    async def register_sensor(self, sensor: Sensor):
        """Register a sensor on the bridge."""
        previous = self._sensors.get(sensor.id)
        self._sensors[sensor.id] = sensor
        self._sensors_values[sensor.id] = None

        # Sensors that are registered after we connected get their invalid values from the bridge now, so
        # they need their own hold. The hold that was started when we connected has probably expired already.
        self._hold_sensor(sensor.id)

        try:
            await self.cmd_rpdo_request(sensor.id, sensor.type)
        except BaseException:
            # Only keep the sensor when the bridge accepted the subscription, so we don't retry it on every reconnect.
            handle = self._sensor_holds.pop(sensor.id, None)
            if handle is not None:
                handle.cancel()
            if previous is None:
                self._sensors.pop(sensor.id, None)
                self._sensors_values.pop(sensor.id, None)
            else:
                self._sensors[sensor.id] = previous
            raise

    async def deregister_sensor(self, sensor: Sensor):
        """Deregister a sensor on the bridge."""
        # Clean up locally first, so the sensor isn't subscribed again on the next reconnect when we can't reach the bridge now.
        handle = self._sensor_holds.pop(sensor.id, None)
        if handle is not None:
            handle.cancel()

        self._sensors.pop(sensor.id, None)
        self._sensors_values.pop(sensor.id, None)

        await self.cmd_rpdo_request(sensor.id, sensor.type, timeout=0)

    async def get_property(self, prop: Property, node_id: Optional[int] = None) -> Any:
        """Get a property and convert to the right type."""
        return await self.get_single_property(prop.unit, prop.subunit, prop.property_id, prop.property_type, node_id=node_id)

    async def get_single_property(self, unit: int, subunit: int, property_id: int, property_type: int = None, node_id: Optional[int] = None) -> Any:
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

    async def get_property_constraints(self, prop: Property, node_id: Optional[int] = None) -> PropertyConstraints:
        """Get the raw value of a numeric property, together with the range and step size the unit accepts, in one request."""
        if prop.property_type not in NUMERIC_PROPERTY_TYPES:
            raise ValueError(f"Property type {prop.property_type} has no range")
        size, signed = NUMERIC_PROPERTY_TYPES[prop.property_type]

        # Request the actual value (0x10), the range (0x20) and the step size (0x40) at once.
        result = await self.cmd_rmi_request(bytes([0x01, prop.unit, prop.subunit, 0x70, prop.property_id]), node_id=node_id)

        message = bytes(result.message)
        if len(message) != 4 * size:
            raise ValueError(f"Unexpected response length {len(message)} for a value with its range and step size")
        value, minimum, maximum, step = (int.from_bytes(message[i : i + size], byteorder="little", signed=signed) for i in range(0, 4 * size, size))
        return PropertyConstraints(value=value, minimum=minimum, maximum=maximum, step=step)

    async def get_multiple_properties(self, unit: int, subunit: int, property_ids: List[int], node_id: Optional[int] = None) -> Any:
        """Get multiple properties."""
        result = await self.cmd_rmi_request(bytestring([0x02, unit, subunit, 0x01, 0x10 | len(property_ids), bytes(property_ids)]), node_id=node_id)

        return result.message

    async def set_property(self, unit: int, subunit: int, property_id: int, value: int, node_id: Optional[int] = None) -> Any:
        """Set a property."""
        result = await self.cmd_rmi_request(bytes([0x03, unit, subunit, property_id, value]), node_id=node_id)

        return result.message

    async def set_property_typed(self, unit: int, subunit: int, property_id: int, value: int, pdo_type: PdoType, node_id: Optional[int] = None) -> Any:
        """Set a typed property."""
        value_bytes = encode_pdo_value(value, pdo_type)
        message_bytes = bytes([0x03, unit, subunit, property_id]) + value_bytes

        result = await self.cmd_rmi_request(message_bytes, node_id=node_id)

        return result.message

    def _require_comfoclime_node_id(self) -> int:
        """Return the node id of the ComfoClime, or raise when it isn't on the bus."""
        node_id = self.comfoclime_node_id
        if node_id is None:
            raise ComfoClimeNotFoundException("The bridge has not announced a ComfoClime")
        return node_id

    async def get_comfoclime_property(self, prop: Property) -> Any:
        """Get a property from the ComfoClime node."""
        return await self.get_property(prop, node_id=self._require_comfoclime_node_id())

    async def set_comfoclime_property(self, prop: Property, value: int) -> Any:
        """Set a property on the ComfoClime node."""
        return await self.set_property_typed(
            prop.unit,
            prop.subunit,
            prop.property_id,
            value,
            prop.property_type,
            node_id=self._require_comfoclime_node_id(),
        )

    def _sensor_callback(self, sensor_id, sensor_value):
        """Callback function for sensor updates."""
        if self._sensor_callback_fn is None:
            return

        sensor = self._sensors.get(sensor_id)
        if sensor is None:
            _LOGGER.error("Unknown sensor id: %s", sensor_id)
            return

        self._sensors_values[sensor_id] = sensor_value

        # The bridge sends invalid (zero) values right after we subscribe to a sensor, so we hold them back.
        # A non-zero value is a real value, so we can release the hold and emit it right away.
        if sensor_id in self._sensor_holds:
            if not sensor_value:
                return

            _LOGGER.debug("Got a valid value for sensor %s, releasing the hold", sensor_id)
            self._sensor_holds.pop(sensor_id).cancel()

        if sensor.value_fn:
            val = sensor.value_fn(sensor_value)
        else:
            val = round(sensor_value, 2)
        self._sensor_callback_fn(sensor, val)

    def _alarm_callback(self, node_id, alarm):
        """Callback function for alarm updates."""
        if self._alarm_callback_fn is None:
            return

        node = self._nodes.get(node_id)
        if node is None or not node.is_ventilation_unit:
            # The error tables only describe the ventilation unit, other nodes use their own bits.
            error_messages = {}
        elif alarm.swProgramVersion <= 3222278144:
            # Firmware 1.4.0 and below
            error_messages = ERRORS_140
        else:
            error_messages = ERRORS

        # Don't fail on bits we don't know, this would end the read loop.
        errors = {bit: error_messages.get(bit, f"Unknown error {bit}") for bit in bytearray_to_bits(alarm.errors)}
        self._alarm_callback_fn(node_id, errors)

    async def get_timer(self, subunit: int, timer: int) -> TimerEntry:
        """Get a timer of the SCHEDULE unit."""
        result = await self.cmd_rmi_request(bytes([0x83, UNIT_SCHEDULE, subunit, timer]))

        active, delay, duration, remaining, value = struct.unpack_from("<BiiiB", result.message)

        return TimerEntry(active == 1, delay, duration, remaining, value)

    async def set_timer(self, subunit: int, timer: int, value: int, duration: int = -1):
        """Start a timer of the SCHEDULE unit, that sets the value for the duration in seconds (-1 is until it is cancelled)."""
        await self.cmd_rmi_request(bytes([0x84, UNIT_SCHEDULE, subunit, timer]) + struct.pack("<iiB", 0, duration, value))

    async def cancel_timer(self, subunit: int, timer: int):
        """Cancel a timer of the SCHEDULE unit."""
        await self.cmd_rmi_request(bytes([0x85, UNIT_SCHEDULE, subunit, timer]))

    async def get_mode(self):
        """Get the current mode."""
        timer = await self.get_timer(SCHEDULE_MANUAL_MODE, TIMER_DEFAULT)

        return VentilationMode.MANUAL if timer.active else VentilationMode.AUTO

    async def set_mode(self, mode: Literal["auto", "manual"]):
        """Set ventilation mode, cancelling the temporary speed override for auto."""
        if mode == VentilationMode.AUTO:
            await self.cancel_timer(SCHEDULE_MANUAL_MODE, TIMER_DEFAULT)
            await self.cancel_timer(SCHEDULE_PRESET, TIMER_DEFAULT)
        elif mode == VentilationMode.MANUAL:
            # A duration of 1 lets the unit pick its default, like the official app: until cancelled in manual mode, 2 hours in auto mode.
            await self.set_timer(SCHEDULE_MANUAL_MODE, TIMER_DEFAULT, 0x01, duration=1)
        else:
            raise ValueError(f"Invalid mode: {mode}")

    async def get_speed(self):
        """Get the ventilation speed (away / low / medium / high), or None when no speed is set and the unit follows its schedule."""
        timer = await self.get_timer(SCHEDULE_PRESET, TIMER_DEFAULT)
        if not timer.active:
            return None
        speed = timer.value

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
        """Set the ventilation speed (away / low / medium / high)."""
        if speed == VentilationSpeed.AWAY:
            value = 0x00
        elif speed == VentilationSpeed.LOW:
            value = 0x01
        elif speed == VentilationSpeed.MEDIUM:
            value = 0x02
        elif speed == VentilationSpeed.HIGH:
            value = 0x03
        else:
            raise ValueError(f"Invalid speed: {speed}")

        # A duration of 1 lets the unit pick its default, like the official app: until cancelled in manual mode, 2 hours in auto mode.
        await self.set_timer(SCHEDULE_PRESET, TIMER_DEFAULT, value, duration=1)

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
            case _:
                raise ValueError(f"Invalid speed: {speed}")

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
            case _:
                raise ValueError(f"Invalid speed: {speed}")

        await self.set_property_typed(UNIT_VENTILATIONCONFIG, SUBUNIT_01, property_id, desired_flow, PdoType.TYPE_CN_INT16)

    async def get_bypass(self):
        """Get the bypass mode (auto / on / off)."""
        timer = await self.get_timer(SCHEDULE_BYPASS, TIMER_DEFAULT)
        if not timer.active:
            return VentilationSetting.AUTO
        mode = timer.value

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
            await self.cancel_timer(SCHEDULE_BYPASS, TIMER_DEFAULT)
        elif mode == VentilationSetting.ON:
            await self.set_timer(SCHEDULE_BYPASS, TIMER_DEFAULT, 0x01, timeout)
        elif mode == VentilationSetting.OFF:
            await self.set_timer(SCHEDULE_BYPASS, TIMER_DEFAULT, 0x02, timeout)
        else:
            raise ValueError(f"Invalid mode: {mode}")

    async def get_balance_mode(self):
        """Get the ventilation balance mode (balance / supply only / exhaust only)."""
        supply_only = (await self.get_timer(SCHEDULE_SUPPLY_ONLY, TIMER_DEFAULT)).active
        exhaust_only = (await self.get_timer(SCHEDULE_EXHAUST_ONLY, TIMER_DEFAULT)).active

        if supply_only == exhaust_only:
            return VentilationBalance.BALANCE
        if supply_only:
            return VentilationBalance.SUPPLY_ONLY
        return VentilationBalance.EXHAUST_ONLY

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
        return (await self.get_timer(SCHEDULE_PRESET, TIMER_BOOST)).active

    async def set_boost(self, mode: bool, timeout=3600):
        """Activate boost mode."""
        if mode:
            await self.cmd_rmi_request(bytestring([0x84, UNIT_SCHEDULE, SUBUNIT_01, 0x06, 0x00, 0x00, 0x00, 0x00, timeout.to_bytes(4, "little", signed=True), 0x03]))
        else:
            await self.cmd_rmi_request(bytes([0x85, UNIT_SCHEDULE, SUBUNIT_01, 0x06]))

    async def get_away(self):
        """Get away mode."""
        return (await self.get_timer(SCHEDULE_PRESET, TIMER_AWAY)).active

    async def set_away(self, mode: bool, timeout=3600):
        """Activate away mode."""
        if mode:
            await self.cmd_rmi_request(bytestring([0x84, UNIT_SCHEDULE, SUBUNIT_01, 0x0B, 0x00, 0x00, 0x00, 0x00, timeout.to_bytes(4, "little", signed=True), 0x00]))
        else:
            await self.cmd_rmi_request(bytes([0x85, UNIT_SCHEDULE, SUBUNIT_01, 0x0B]))

    async def get_comfocool_mode(self):
        """Get the current comfocool mode."""
        # The timer is the "off" override.
        timer = await self.get_timer(SCHEDULE_COMFOCOOL, TIMER_DEFAULT)

        return ComfoCoolMode.OFF if timer.active else ComfoCoolMode.AUTO

    async def set_comfocool_mode(self, mode: Literal["auto", "off"], timeout=-1):
        """Set the comfocool mode (auto / off)."""
        if mode == ComfoCoolMode.AUTO:
            await self.cancel_timer(SCHEDULE_COMFOCOOL, TIMER_DEFAULT)
        elif mode == ComfoCoolMode.OFF:
            await self.set_timer(SCHEDULE_COMFOCOOL, TIMER_DEFAULT, 0x00, timeout)
        else:
            raise ValueError(f"Invalid mode: {mode}")

    async def get_temperature_profile(self):
        """Get the temperature profile (warm / normal / cool), or None when no profile is set and the unit follows its schedule."""
        timer = await self.get_timer(SCHEDULE_TEMPERATURE_PROFILE, TIMER_DEFAULT)
        if not timer.active:
            return None
        mode = timer.value

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
