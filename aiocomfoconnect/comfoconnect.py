""" ComfoConnect Bridge API abstraction """

from __future__ import annotations

import asyncio
import logging
import struct
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, List, Literal, Optional

from aiocomfoconnect import Bridge
from aiocomfoconnect.bridge import Message
from aiocomfoconnect.const import (
    ERRORS,
    ERRORS_140,
    NUMERIC_PROPERTY_TYPES,
    UNIT_ERROR,
    UNIT_SCHEDULE,
    ComfoCoolMode,
    ConnectionState,
    PdoType,
    ProductId,
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
    AioComfoConnectSessionClosed,
    AioComfoConnectTimeout,
    ComfoClimeNotFoundException,
    ComfoConnectError,
    ComfoConnectNotAllowed,
    ComfoConnectOtherSession,
    NodeNotFoundException,
)
from aiocomfoconnect.properties import (
    PROPERTY_ARTICLE,
    PROPERTY_FIRMWARE_VERSION,
    PROPERTY_HARDWARE_VERSION,
    PROPERTY_MODEL,
    PROPERTY_NAME,
    PROPERTY_SERIAL_NUMBER,
    Property,
    PropertyConstraints,
)
from aiocomfoconnect.sensors import Sensor
from aiocomfoconnect.util import bytearray_to_bits, encode_pdo_value, version_decode

_LOGGER = logging.getLogger(__name__)

# How long the reconnect loop waits before it connects again after the connection was lost, and after a failed attempt.
RECONNECT_DELAY = 1
RECONNECT_RETRY_DELAY = 5
# How long it waits when the bridge closed our session, or when another app has the only session that old firmware
# allows. We never take the session over, so this is how often we check whether the other app is gone.
RECONNECT_SESSION_CLOSED_DELAY = 60
# How many seconds the connection may be idle before we check that the bridge still answers.
HEARTBEAT_INTERVAL = 30

# The settings of the speed, bypass and temperature profile timers. The index is the value of the timer.
SPEEDS = (VentilationSpeed.AWAY, VentilationSpeed.LOW, VentilationSpeed.MEDIUM, VentilationSpeed.HIGH)
BYPASS_MODES = (VentilationSetting.AUTO, VentilationSetting.ON, VentilationSetting.OFF)
TEMPERATURE_PROFILES = (VentilationTemperatureProfile.NORMAL, VentilationTemperatureProfile.COOL, VentilationTemperatureProfile.WARM)


# The size in bytes of the value of the property types that aren't a string.
VALUE_SIZES = {PdoType.TYPE_CN_BOOL: 1, PdoType.TYPE_CN_VERSION: 4} | {pdo_type: size for pdo_type, (size, _) in NUMERIC_PROPERTY_TYPES.items()}


def _decode_value(property_type: Optional[int], raw: bytes) -> Any:
    """Decode the raw value of a property of the given type. A type we don't know is returned as bytes."""
    if property_type == PdoType.TYPE_CN_STRING:
        return raw.decode("utf-8").rstrip("\x00")
    if property_type in NUMERIC_PROPERTY_TYPES:
        _, signed = NUMERIC_PROPERTY_TYPES[property_type]
        return int.from_bytes(raw, byteorder="little", signed=signed)
    if property_type == PdoType.TYPE_CN_BOOL:
        return bool(raw[0])
    if property_type == PdoType.TYPE_CN_VERSION:
        return version_decode(int.from_bytes(raw, byteorder="little"))
    return raw


def _property_value(prop: Property, value: Any) -> Any:
    """Return the option or the scaled value of a decoded property value."""
    if prop.options is None:
        return prop.scaled(value)
    if value not in prop.options:
        raise ValueError(f"Invalid value: {value}")
    return prop.options[value]


@dataclass
class NodeInfo:
    """What a node tells about itself."""

    name: str
    model: str
    article_number: str
    serial_number: str
    firmware: str
    hardware_version: int


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
        sensor_callback=None,
        alarm_callback=None,
        sensor_delay=5,
        connect_timeout=30,
        bridge_type: int = 0,
        heartbeat_interval: Optional[float] = HEARTBEAT_INTERVAL,
        connection_state_callback: Optional[Callable[[str], None]] = None,
    ):
        """Initialize the ComfoConnect class.

        When we received nothing for heartbeat_interval seconds, we ask the bridge for its time, and reconnect when it
        doesn't answer. This detects a bridge that stopped answering without closing the connection. None disables it.

        The connection_state_callback is called with a ConnectionState when the state of the session changes.
        """
        super().__init__(host, uuid, bridge_type)

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
        if not self.sensor_delay:
            return

        # Restart the hold if the sensor is already held.
        handle = self._sensor_holds.pop(sensor_id, None)
        if handle is not None:
            handle.cancel()

        _LOGGER.debug("Holding sensor %s for %s second(s)", sensor_id, self.sensor_delay)
        self._sensors_values[sensor_id] = None
        self._sensor_holds[sensor_id] = asyncio.get_running_loop().call_later(self.sensor_delay, self._unhold_sensor, sensor_id)

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

        # Don't take over the session of another app. Bridges allow several sessions; old firmware that allows only one
        # refuses ours with OTHER_SESSION while the other app has it, and we try again later.
        await self.cmd_start_session()

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
                read_task = self._read_task
                if read_task.done() and not read_task.cancelled() and isinstance(read_task.exception(), AioComfoConnectSessionClosed):
                    _LOGGER.info("The bridge closed our session. Reconnecting in %s seconds...", RECONNECT_SESSION_CLOSED_DELAY)
                    delay = RECONNECT_SESSION_CLOSED_DELAY
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
                    except ComfoConnectOtherSession:
                        _LOGGER.info("Another app has the session. Retrying in %s seconds...", RECONNECT_SESSION_CLOSED_DELAY)
                        delay = RECONNECT_SESSION_CLOSED_DELAY
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

    def cmd_rmi_request(self, message, node_id: Optional[int] = None) -> Awaitable[Message]:
        """Sends a RMI request, but only once the session is up.

        While we (re)connect, the connection is open before the session has started and the ventilation unit is known.
        A command in that window fails like one while disconnected.
        """
        if self._connection_state != ConnectionState.CONNECTED:
            raise AioComfoConnectNotConnected("Not connected to bridge")
        return super().cmd_rmi_request(message, node_id)

    async def _send(self, request, request_type, params: dict = None, reply: bool = True, timeout: float = None) -> Message:
        """Send a request, and close the connection when the bridge dropped our session.

        The bridge can drop our session without closing the connection, e.g. when another app takes over a session with our
        uuid. It then answers every request with NOT_ALLOWED (or OTHER_SESSION). Closing the connection lets the reconnect
        loop start a new session. The request still raises its error.
        """
        try:
            return await super()._send(request, request_type, params, reply, timeout)
        except (ComfoConnectNotAllowed, ComfoConnectOtherSession):
            if self._connection_state == ConnectionState.CONNECTED and self._writer is not None:
                _LOGGER.warning("The bridge dropped our session, reconnecting")
                self._writer.close()
            raise

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

    def _node_id_for(self, prop: Property, node_id: Optional[int] = None) -> Optional[int]:
        """Return the node id to send a request for the property to: node_id when given, else the first node of its product.

        None means the ventilation unit, that cmd_rmi_request resolves itself.
        """
        if node_id is not None or prop.product is None:
            return node_id
        node_ids = [node.node_id for node in self.nodes.values() if node.product_id == prop.product]
        if not node_ids:
            exception = ComfoClimeNotFoundException if prop.product == ProductId.COMFOCLIME else NodeNotFoundException
            raise exception(f"The bridge has not announced a node with product id {prop.product}")
        return min(node_ids)

    async def get_property(self, prop: Property, node_id: Optional[int] = None) -> Any:
        """Get a property from the node it lives on (or node_id), and convert it to the right type, its option or its scaled value."""
        value = await self.get_single_property(prop.unit, prop.subunit, prop.property_id, prop.property_type, node_id=self._node_id_for(prop, node_id))
        return _property_value(prop, value)

    async def get_properties(self, props: List[Property], node_id: Optional[int] = None) -> List[Any]:
        """Get several properties of one node in one request, converted like get_property.

        The properties are read in groups of consecutive properties of the same unit and subunit, of at most 7 like the
        official app. A ValueError is raised for properties on different nodes, or of a type whose size we don't know.
        """
        node_ids = {self._node_id_for(prop, node_id) for prop in props}
        if len(node_ids) > 1:
            raise ValueError("The properties live on different nodes")
        for prop in props:
            if prop.property_type != PdoType.TYPE_CN_STRING and prop.property_type not in VALUE_SIZES:
                raise ValueError(f"Property type {prop.property_type} can't be read with other properties")

        groups: List[List[Property]] = []
        for prop in props:
            if groups and len(groups[-1]) < 7 and (groups[-1][0].unit, groups[-1][0].subunit) == (prop.unit, prop.subunit):
                groups[-1].append(prop)
            else:
                groups.append([prop])

        request = [0x02, len(groups)]
        for group in groups:
            request += [group[0].unit, group[0].subunit, 0x10 | len(group)] + [prop.property_id for prop in group]
        result = await self.cmd_rmi_request(bytes(request), node_id=node_ids.pop() if node_ids else None)

        # The values follow each other: a string ends with a NUL, the other types have a fixed size.
        message = bytes(result.message)
        values = []
        for prop in props:
            if prop.property_type == PdoType.TYPE_CN_STRING:
                size = message.find(b"\x00") + 1 or len(message)
            else:
                size = VALUE_SIZES[prop.property_type]
            if len(message) < size:
                raise ValueError(f"The response is too short for the value of property {prop.property_id}")
            values.append(_property_value(prop, _decode_value(prop.property_type, message[:size])))
            message = message[size:]
        if message:
            raise ValueError(f"Unexpected {len(message)} bytes at the end of the response")
        return values

    async def get_node_info(self, node_id: Optional[int] = None) -> NodeInfo:
        """Get the NodeInfo of a node (the ventilation unit by default), in one request."""
        props = [PROPERTY_NAME, PROPERTY_MODEL, PROPERTY_ARTICLE, PROPERTY_SERIAL_NUMBER, PROPERTY_FIRMWARE_VERSION, PROPERTY_HARDWARE_VERSION]
        return NodeInfo(*await self.get_properties(props, node_id))

    async def get_single_property(self, unit: int, subunit: int, property_id: int, property_type: int = None, node_id: Optional[int] = None) -> Any:
        """Get a property and convert to the right type."""
        result = await self.cmd_rmi_request(bytes([0x01, unit, subunit, 0x10, property_id]), node_id=node_id)
        return _decode_value(property_type, result.message)

    async def get_property_constraints(self, prop: Property, node_id: Optional[int] = None) -> PropertyConstraints:
        """Get the (scaled) value of a numeric property, together with the range and step size the unit accepts, in one request."""
        if prop.property_type not in NUMERIC_PROPERTY_TYPES:
            raise ValueError(f"Property type {prop.property_type} has no range")
        size, signed = NUMERIC_PROPERTY_TYPES[prop.property_type]

        # Request the actual value (0x10), the range (0x20) and the step size (0x40) at once.
        result = await self.cmd_rmi_request(bytes([0x01, prop.unit, prop.subunit, 0x70, prop.property_id]), node_id=self._node_id_for(prop, node_id))

        message = bytes(result.message)
        if len(message) != 4 * size:
            raise ValueError(f"Unexpected response length {len(message)} for a value with its range and step size")
        value, minimum, maximum, step = (int.from_bytes(message[i : i + size], byteorder="little", signed=signed) for i in range(0, 4 * size, size))
        return PropertyConstraints(value=prop.scaled(value), minimum=prop.scaled(minimum), maximum=prop.scaled(maximum), step=prop.scaled(step))

    async def set_property(self, prop: Property, value: int | float | str, node_id: Optional[int] = None) -> Any:
        """Set a property on the node it lives on (or node_id), encoded for its type.

        A property with options takes an option, a scaled property takes the scaled value.
        """
        if prop.scale is not None:
            value = round(value / prop.scale)
        if prop.options is not None:
            values = {option: raw for raw, option in prop.options.items()}
            if value not in values:
                raise ValueError(f"Invalid option: {value}")
            value = values[value]

        message = bytes([0x03, prop.unit, prop.subunit, prop.property_id]) + encode_pdo_value(value, prop.property_type)
        result = await self.cmd_rmi_request(message, node_id=self._node_id_for(prop, node_id))

        return result.message

    def _sensor_callback(self, sensor_id, sensor_value):
        """Callback function for sensor updates."""
        if self._sensor_callback_fn is None:
            return

        sensor = self._sensors.get(sensor_id)
        if sensor is None:
            # After a quick reconnect, the bridge can still push the sensors of our previous session before we subscribe again.
            _LOGGER.debug("Ignoring a value for sensor %s, that we are not subscribed to", sensor_id)
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
        if timer.value >= len(SPEEDS):
            raise ValueError(f"Invalid speed: {timer.value}")

        return SPEEDS[timer.value]

    async def set_speed(self, speed: Literal["away", "low", "medium", "high"]):
        """Set the ventilation speed (away / low / medium / high)."""
        if speed not in SPEEDS:
            raise ValueError(f"Invalid speed: {speed}")

        # A duration of 1 lets the unit pick its default, like the official app: until cancelled in manual mode, 2 hours in auto mode.
        await self.set_timer(SCHEDULE_PRESET, TIMER_DEFAULT, SPEEDS.index(speed), duration=1)

    async def get_bypass(self):
        """Get the bypass mode (auto / on / off)."""
        timer = await self.get_timer(SCHEDULE_BYPASS, TIMER_DEFAULT)
        if not timer.active:
            return VentilationSetting.AUTO
        if timer.value >= len(BYPASS_MODES):
            raise ValueError(f"Invalid mode: {timer.value}")

        return BYPASS_MODES[timer.value]

    async def set_bypass(self, mode: Literal["auto", "on", "off"], timeout=-1):
        """Set the bypass mode (auto / on / off)."""
        if mode == VentilationSetting.AUTO:
            await self.cancel_timer(SCHEDULE_BYPASS, TIMER_DEFAULT)
        elif mode in BYPASS_MODES:
            await self.set_timer(SCHEDULE_BYPASS, TIMER_DEFAULT, BYPASS_MODES.index(mode), timeout)
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
            await self.cancel_timer(SCHEDULE_SUPPLY_ONLY, TIMER_DEFAULT)
            await self.cancel_timer(SCHEDULE_EXHAUST_ONLY, TIMER_DEFAULT)
        elif mode == VentilationBalance.SUPPLY_ONLY:
            await self.set_timer(SCHEDULE_SUPPLY_ONLY, TIMER_DEFAULT, 0x01, timeout)
            await self.cancel_timer(SCHEDULE_EXHAUST_ONLY, TIMER_DEFAULT)
        elif mode == VentilationBalance.EXHAUST_ONLY:
            await self.cancel_timer(SCHEDULE_SUPPLY_ONLY, TIMER_DEFAULT)
            await self.set_timer(SCHEDULE_EXHAUST_ONLY, TIMER_DEFAULT, 0x01, timeout)
        else:
            raise ValueError(f"Invalid mode: {mode}")

    async def get_boost(self):
        """Get boost mode."""
        return (await self.get_timer(SCHEDULE_PRESET, TIMER_BOOST)).active

    async def set_boost(self, mode: bool, timeout=3600):
        """Activate boost mode."""
        if mode:
            await self.set_timer(SCHEDULE_PRESET, TIMER_BOOST, 0x03, timeout)
        else:
            await self.cancel_timer(SCHEDULE_PRESET, TIMER_BOOST)

    async def get_away(self):
        """Get away mode."""
        return (await self.get_timer(SCHEDULE_PRESET, TIMER_AWAY)).active

    async def set_away(self, mode: bool, timeout=3600):
        """Activate away mode."""
        if mode:
            await self.set_timer(SCHEDULE_PRESET, TIMER_AWAY, 0x00, timeout)
        else:
            await self.cancel_timer(SCHEDULE_PRESET, TIMER_AWAY)

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
        if timer.value >= len(TEMPERATURE_PROFILES):
            raise ValueError(f"Invalid mode: {timer.value}")

        return TEMPERATURE_PROFILES[timer.value]

    async def set_temperature_profile(self, profile: Literal["warm", "normal", "cool"], timeout=-1):
        """Set the temperature profile (warm / normal / cool)."""
        if profile not in TEMPERATURE_PROFILES:
            raise ValueError(f"Invalid profile: {profile}")

        await self.set_timer(SCHEDULE_TEMPERATURE_PROFILE, TIMER_DEFAULT, TEMPERATURE_PROFILES.index(profile), timeout)

    async def clear_errors(self):
        """Clear the errors."""
        await self.cmd_rmi_request(bytes([0x82, UNIT_ERROR, 0x01]))
