""" ComfoConnect Bridge API """

from __future__ import annotations

import asyncio
import itertools
import logging
import struct
from asyncio import StreamReader, StreamWriter
from dataclasses import dataclass
from typing import Awaitable, Callable, Dict, Iterator, Optional, Set

from google.protobuf.message import DecodeError
from google.protobuf.message import Message as ProtobufMessage

from .const import VENTILATION_UNIT_PRODUCT_IDS
from .exceptions import (
    AioComfoConnectNotConnected,
    AioComfoConnectNotReachable,
    AioComfoConnectTimeout,
    ComfoConnectBadRequest,
    ComfoConnectError,
    ComfoConnectInternalError,
    ComfoConnectNoResources,
    ComfoConnectNotAllowed,
    ComfoConnectNotExist,
    ComfoConnectNotReachable,
    ComfoConnectOtherSession,
    ComfoConnectRmiError,
    VentilationUnitNotFoundException,
)
from .protobuf import zehnder_pb2

_LOGGER = logging.getLogger(__name__)

TIMEOUT = 5
GATEWAY_TYPE_PRO = 2

# How long we wait for the bridge to announce the ventilation unit before we give up.
NODE_DISCOVERY_TIMEOUT = 5


class SelfDeregistrationError(Exception):
    """Exception raised when trying to deregister self."""


@dataclass(frozen=True)
class Node:
    """A node on the ComfoNet bus, as announced by a CnNodeNotification."""

    node_id: int
    product_id: int
    zone_id: int
    mode: int

    @property
    def is_offline(self) -> bool:
        """Returns True if this node is no longer available on the bus."""
        # pylint: disable=no-member
        if self.mode == zehnder_pb2.CnNodeNotification.NODE_LEGACY:
            # Legacy nodes don't report a mode, they are offline when they have no product id.
            return self.product_id == 0
        return self.mode == zehnder_pb2.CnNodeNotification.NODE_OFFLINE

    @property
    def is_ventilation_unit(self) -> bool:
        """Returns True if this node is the ventilation unit that handles RMI commands."""
        return self.product_id in VENTILATION_UNIT_PRODUCT_IDS


class EventBus:
    """An event bus for async replies."""

    def __init__(self):
        self._listeners: Dict[int, Set[asyncio.Future]] = {}

    @property
    def listeners(self) -> Dict[int, Set[asyncio.Future]]:
        """Expose listeners for diagnostic purposes (primarily tests)."""
        return self._listeners

    def add_listener(self, event_name: int, future: asyncio.Future):
        """Add a listener to the event bus."""
        _LOGGER.debug("Adding listener for event %s", event_name)
        self._listeners.setdefault(event_name, set()).add(future)

    def emit(self, event_name: int, event):
        """Emit an event to the event bus."""
        _LOGGER.debug("Emitting for event %s", event_name)
        futures = self._listeners.pop(event_name, set())
        for future in futures:
            if future.done():
                continue
            if isinstance(event, Exception):
                future.set_exception(event)
            else:
                future.set_result(event)

    def fail_all(self, exc: Exception):
        """Fail all pending listeners with the provided exception."""
        pending = list(self._listeners.values())
        self._listeners.clear()
        for futures in pending:
            for future in futures:
                if future.done():
                    continue
                future.set_exception(exc)


class Bridge:
    """ComfoConnect LAN C / PRO API."""

    PORT = 56747

    def __init__(
        self,
        host: str,
        uuid: str,
        loop: Optional[asyncio.AbstractEventLoop] = None,
        bridge_type: int = 0,
    ):
        self.host: str = host
        self.uuid: str = uuid
        self.bridge_type: int = bridge_type
        self._local_uuid: Optional[str] = None

        self._reader: Optional[StreamReader] = None
        self._writer: Optional[StreamWriter] = None
        self._reference: Optional[Iterator[int]] = None

        self._event_bus: Optional[EventBus] = None

        self._nodes: Dict[int, Node] = {}
        self._ventilation_node_found: Optional[asyncio.Event] = None

        self.__sensor_callback_fn: Optional[Callable[[int, int], None]] = None
        self.__alarm_callback_fn: Optional[Callable[[int, ProtobufMessage], None]] = None

        self._loop: Optional[asyncio.AbstractEventLoop] = loop
        self._read_task = None

    def __repr__(self):
        return f"<Bridge {self.host}, UID={self.uuid}>"

    def set_sensor_callback(self, callback: Optional[Callable[[int, int], None]]):
        """Set a callback to be called when a message is received."""
        self.__sensor_callback_fn = callback

    def set_alarm_callback(self, callback: Optional[Callable[[int, ProtobufMessage], None]]):
        """Set a callback to be called when an alarm is received."""
        self.__alarm_callback_fn = callback

    async def connect(self, uuid: str):
        """Connect to the bridge and start reading messages."""
        await self._open_connection(uuid)

    async def register(self, uuid: str, name: str, pin: int) -> bool:
        """Register this app on the bridge and start a session.

        For LAN C bridges, attempts to start a session first; if the session
        succeeds the app is already registered and no re-registration occurs.
        For Pro bridges, registers directly to avoid a connection timeout that
        the Pro issues when the app is not yet registered.

        Returns True if the app was newly registered, False if it was already registered.
        """
        await self._open_connection(uuid)
        if self.bridge_type != GATEWAY_TYPE_PRO:
            # LAN C: check whether we are already registered by starting a session.
            try:
                await self.cmd_start_session(True)
                return False  # Already registered; session is now active.
            except ComfoConnectNotAllowed:
                pass  # Not registered yet; fall through to register below.
        await self.cmd_register_app(uuid, name, pin)
        await self.cmd_start_session(True)
        return True

    async def _open_connection(self, uuid: str):
        """Open TCP connection to the bridge and start reading messages."""
        if self.is_connected():
            _LOGGER.warning("Already connected to bridge %s", self.host)
            return

        # Get the running loop if not provided
        if self._loop is None:
            self._loop = asyncio.get_running_loop()

        _LOGGER.debug("Connecting to bridge %s", self.host)
        try:
            self._reader, self._writer = await asyncio.wait_for(asyncio.open_connection(self.host, self.PORT), TIMEOUT)
        except asyncio.TimeoutError as exc:
            # Keep this before OSError, since TimeoutError is a subclass of it.
            _LOGGER.warning("Timeout while connecting to bridge %s", self.host)
            raise AioComfoConnectTimeout("Timeout while connecting to bridge") from exc
        except OSError as exc:
            # The bridge refused the connection, is gone from the network, or its hostname doesn't resolve.
            _LOGGER.warning("Could not connect to bridge %s: %s", self.host, exc)
            raise AioComfoConnectNotReachable(f"Could not connect to bridge: {exc}") from exc

        self._reference = itertools.count(1)
        self._local_uuid = uuid
        self._event_bus = EventBus()

        # The bridge announces its nodes at the start of every session, so forget what we knew.
        self._nodes = {}
        self._ventilation_node_found = asyncio.Event()

        # Start background task to read messages
        self._read_task = self._loop.create_task(self._read_messages())
        _LOGGER.debug("Connected to bridge %s", self.host)

    async def _read_messages(self):
        """Read messages from the bridge until disconnected or cancelled."""
        try:
            while True:
                await self._process_message()
        except asyncio.CancelledError:
            _LOGGER.debug("Message reading cancelled")
            raise
        except AioComfoConnectNotConnected as exc:
            _LOGGER.info("Disconnected from bridge")
            self._notify_pending_futures(exc)
            raise
        except Exception as exc:
            _LOGGER.error("Unexpected error reading messages: %s", exc, exc_info=True)
            self._notify_pending_futures(AioComfoConnectNotConnected("Unexpected error during read"))
            raise

    def _process_node_notification(self, msg: ProtobufMessage):
        """Keep track of the nodes that are available on the ComfoNet bus."""
        node = Node(node_id=msg.nodeId, product_id=msg.productId, zone_id=msg.zoneId, mode=msg.mode)

        if node.is_offline:
            _LOGGER.debug("Node %s went offline", node.node_id)
            self._nodes.pop(node.node_id, None)
            return

        _LOGGER.debug("Discovered node %s with product id %s in zone %s", node.node_id, node.product_id, node.zone_id)
        self._nodes[node.node_id] = node

        if node.is_ventilation_unit and self._ventilation_node_found is not None:
            self._ventilation_node_found.set()

    @property
    def nodes(self) -> Dict[int, Node]:
        """The nodes that the bridge has announced for the current session, keyed by node id."""
        return self._nodes

    @property
    def ventilation_node_id(self) -> Optional[int]:
        """The node id of the ventilation unit, or None when the bridge hasn't announced it (yet)."""
        candidates = [node.node_id for node in self._nodes.values() if node.is_ventilation_unit]
        return min(candidates) if candidates else None

    async def wait_for_ventilation_node(self, timeout: float = None) -> int:
        """Wait until the bridge has announced the ventilation unit and return its node id.

        Raises VentilationUnitNotFoundException when the bridge doesn't announce one in time.
        """
        if timeout is None:
            timeout = NODE_DISCOVERY_TIMEOUT

        if self._ventilation_node_found is not None:
            try:
                await asyncio.wait_for(self._ventilation_node_found.wait(), timeout)
            except asyncio.TimeoutError:
                pass

        node_id = self.ventilation_node_id
        if node_id is None:
            raise VentilationUnitNotFoundException(f"The bridge did not announce a ventilation unit within {timeout} seconds")

        return node_id

    def _notify_pending_futures(self, exc: Exception):
        """Fail all pending listeners so callers do not hang."""
        if self._event_bus is None:
            return
        self._event_bus.fail_all(exc)

    async def disconnect(self):
        """Disconnect from the bridge."""
        if not self.is_connected():
            return

        _LOGGER.debug("Disconnecting from bridge %s", self.host)

        # Cancel the read task
        if self._read_task and not self._read_task.done():
            self._read_task.cancel()
            try:
                await self._read_task
            except asyncio.CancelledError:
                pass

        self._notify_pending_futures(AioComfoConnectNotConnected("Disconnected"))

        # Close the connection
        if self._writer:
            self._writer.close()
            await self._writer.wait_closed()

        # Clear state
        self._reader = None
        self._writer = None
        self._read_task = None
        self._event_bus = None
        self._reference = None
        self._nodes = {}
        self._ventilation_node_found = None

    def is_connected(self) -> bool:
        """Returns True if the bridge is connected."""
        return self._writer is not None and not self._writer.is_closing()

    async def _send(self, request, request_type, params: dict = None, reply: bool = True, timeout: float = None) -> Message:
        """Sends a command and wait for a response if the request is known to return a result.

        Supports concurrent requests through atomic reference allocation and lock-free sending.
        Multiple requests can be in-flight simultaneously, improving throughput.
        """
        if not self.is_connected():
            raise AioComfoConnectNotConnected("Not connected to bridge")

        if timeout is None:
            timeout = TIMEOUT

        if self._loop is None:
            self._loop = asyncio.get_running_loop()

        if not self.is_connected() or self._writer is None or self._reference is None:
            raise AioComfoConnectNotConnected("Not connected to bridge")

        # Allocate reference atomically (thread-safe)
        reference = next(self._reference)

        # Build command and message
        cmd = zehnder_pb2.GatewayOperation()  # pylint: disable=no-member
        cmd.type = request_type
        cmd.reference = reference

        msg = request()
        if params is not None:
            for param, value in params.items():
                if value is not None:
                    setattr(msg, param, value)

        message = Message(cmd, msg, self._local_uuid, self.uuid)

        # Create and register future BEFORE sending to avoid race condition
        # where response arrives before listener is registered
        fut = self._loop.create_future()
        if reply:
            if self._event_bus is None:
                raise RuntimeError("Event bus is not initialized")
            self._event_bus.add_listener(reference, fut)
        else:
            fut.set_result(None)

        # Send message (no lock needed - TCP writes are serialized by the OS)
        _LOGGER.debug("TX %s", message)
        try:
            self._writer.write(message.encode())
            await self._writer.drain()
        except (ConnectionError, OSError) as exc:
            send_exc = AioComfoConnectNotConnected("Connection lost while sending")
            _LOGGER.warning("Failed to send message: %s", exc)
            # Clean up the registered listener on send failure
            if reply and self._event_bus is not None:
                self._event_bus.emit(reference, send_exc)
            elif not fut.done():
                fut.set_exception(send_exc)
            raise send_exc from exc

        # Wait for response
        try:
            return await asyncio.wait_for(fut, timeout)
        except asyncio.TimeoutError as exc:
            _LOGGER.warning("Timeout while waiting for response from bridge")
            raise AioComfoConnectTimeout("Timeout while waiting for response from bridge") from exc

    async def _read(self) -> Message:
        # Read packet size
        msg_len_buf = await self._reader.readexactly(4)

        # Read rest of packet
        msg_len = int.from_bytes(msg_len_buf, byteorder="big")
        msg_buf = await self._reader.readexactly(msg_len)

        # Decode message
        message = Message.decode(msg_buf)

        _LOGGER.debug("RX %s", message)

        # Check status code
        # pylint: disable=no-member
        if message.cmd.result == zehnder_pb2.GatewayOperation.OK:
            pass
        elif message.cmd.result == zehnder_pb2.GatewayOperation.BAD_REQUEST:
            raise ComfoConnectBadRequest(message)
        elif message.cmd.result == zehnder_pb2.GatewayOperation.INTERNAL_ERROR:
            raise ComfoConnectInternalError(message)
        elif message.cmd.result == zehnder_pb2.GatewayOperation.NOT_REACHABLE:
            raise ComfoConnectNotReachable(message)
        elif message.cmd.result == zehnder_pb2.GatewayOperation.OTHER_SESSION:
            raise ComfoConnectOtherSession(message)
        elif message.cmd.result == zehnder_pb2.GatewayOperation.NOT_ALLOWED:
            raise ComfoConnectNotAllowed(message)
        elif message.cmd.result == zehnder_pb2.GatewayOperation.NO_RESOURCES:
            raise ComfoConnectNoResources(message)
        elif message.cmd.result == zehnder_pb2.GatewayOperation.NOT_EXIST:
            raise ComfoConnectNotExist(message)
        elif message.cmd.result == zehnder_pb2.GatewayOperation.RMI_ERROR:
            raise ComfoConnectRmiError(message)

        return message

    async def _process_message(self):
        """Process a message from the bridge."""
        try:
            message = await self._read()

            # pylint: disable=no-member
            if message.cmd.type == zehnder_pb2.GatewayOperation.CnRpdoNotificationType:
                if self.__sensor_callback_fn:
                    self.__sensor_callback_fn(message.msg.pdid, int.from_bytes(message.msg.data, byteorder="little", signed=True))
                else:
                    _LOGGER.info("Unhandled CnRpdoNotificationType since no callback is registered.")

            elif message.cmd.type == zehnder_pb2.GatewayOperation.GatewayNotificationType:
                _LOGGER.debug("Unhandled GatewayNotificationType")

            elif message.cmd.type == zehnder_pb2.GatewayOperation.CnNodeNotificationType:
                self._process_node_notification(message.msg)

            elif message.cmd.type == zehnder_pb2.GatewayOperation.CnAlarmNotificationType:
                if self.__alarm_callback_fn:
                    self.__alarm_callback_fn(message.msg.nodeId, message.msg)
                else:
                    _LOGGER.info("Unhandled CnAlarmNotificationType since no callback is registered.")

            elif message.cmd.type == zehnder_pb2.GatewayOperation.CloseSessionRequestType:
                _LOGGER.info("The Bridge has asked us to close the connection.")
                raise AioComfoConnectNotConnected("Bridge requested connection close")

            elif message.cmd.reference and self._event_bus:
                # Emit to the event bus
                self._event_bus.emit(message.cmd.reference, message.msg)

            else:
                _LOGGER.warning("Unhandled message type %s: %s", message.cmd.type, message)

        except asyncio.IncompleteReadError as exc:
            _LOGGER.info("The connection was closed.")
            disconnect_exc = AioComfoConnectNotConnected("The connection was closed.")
            self._notify_pending_futures(disconnect_exc)
            raise disconnect_exc from exc

        except (ConnectionError, OSError) as exc:
            _LOGGER.info("Connection error: %s", exc)
            disconnect_exc = AioComfoConnectNotConnected("Connection error")
            self._notify_pending_futures(disconnect_exc)
            raise disconnect_exc from exc

        except ComfoConnectError as exc:
            if exc.message.cmd.reference and self._event_bus:
                self._event_bus.emit(exc.message.cmd.reference, exc)

        except DecodeError as exc:
            _LOGGER.error("Failed to decode message: %s", exc)

    def cmd_start_session(self, take_over: bool = False) -> Awaitable[Message]:
        """Starts the session on the device by logging in and optionally disconnecting an already existing session."""
        _LOGGER.debug("StartSessionRequest")
        # pylint: disable=no-member
        return self._send(
            zehnder_pb2.StartSessionRequest,
            zehnder_pb2.GatewayOperation.StartSessionRequestType,
            {"takeover": take_over},
        )

    def cmd_close_session(self) -> Awaitable[Message]:
        """Stops the current session."""
        _LOGGER.debug("CloseSessionRequest")
        # pylint: disable=no-member
        return self._send(
            zehnder_pb2.CloseSessionRequest,
            zehnder_pb2.GatewayOperation.CloseSessionRequestType,
            reply=False,  # Don't wait for a reply
        )

    def cmd_list_registered_apps(self) -> Awaitable[Message]:
        """Returns a list of all the registered clients."""
        _LOGGER.debug("ListRegisteredAppsRequest")
        # pylint: disable=no-member
        return self._send(
            zehnder_pb2.ListRegisteredAppsRequest,
            zehnder_pb2.GatewayOperation.ListRegisteredAppsRequestType,
        )

    def cmd_register_app(self, uuid: str, device_name: str, pin: int) -> Awaitable[Message]:
        """Register a new app by specifying our own uuid, device_name and pin code."""
        _LOGGER.debug("RegisterAppRequest")
        # pylint: disable=no-member
        return self._send(
            zehnder_pb2.RegisterAppRequest,
            zehnder_pb2.GatewayOperation.RegisterAppRequestType,
            {
                "uuid": bytes.fromhex(uuid),
                "devicename": device_name,
                "pin": int(pin),
            },
        )

    def cmd_deregister_app(self, uuid: str) -> Awaitable[Message]:
        """Remove the specified app from the registration list."""
        _LOGGER.debug("DeregisterAppRequest")
        if uuid == self._local_uuid:
            raise SelfDeregistrationError("You should not deregister yourself.")

        # pylint: disable=no-member
        return self._send(
            zehnder_pb2.DeregisterAppRequest,
            zehnder_pb2.GatewayOperation.DeregisterAppRequestType,
            {"uuid": bytes.fromhex(uuid)},
        )

    def cmd_version_request(self) -> Awaitable[Message]:
        """Returns version information."""
        _LOGGER.debug("VersionRequest")
        # pylint: disable=no-member
        return self._send(
            zehnder_pb2.VersionRequest,
            zehnder_pb2.GatewayOperation.VersionRequestType,
        )

    def cmd_time_request(self) -> Awaitable[Message]:
        """Returns the current time on the device."""
        _LOGGER.debug("CnTimeRequest")
        # pylint: disable=no-member
        return self._send(
            zehnder_pb2.CnTimeRequest,
            zehnder_pb2.GatewayOperation.CnTimeRequestType,
        )

    def cmd_node_request(self) -> Awaitable[Message]:
        """(Re)triggers the discovery of the nodes on the ComfoNet bus."""
        _LOGGER.debug("CnNodeRequest")
        # pylint: disable=no-member
        return self._send(
            zehnder_pb2.CnNodeRequest,
            zehnder_pb2.GatewayOperation.CnNodeRequestType,
            reply=False,  # The nodes are reported back as CnNodeNotifications
        )

    def cmd_rmi_request(self, message, node_id: Optional[int] = None) -> Awaitable[Message]:
        """Sends a RMI request to the given node, or to the discovered ventilation unit."""
        _LOGGER.debug("CnRmiRequest")
        if not node_id:
            node_id = self.ventilation_node_id
            if node_id is None:
                raise VentilationUnitNotFoundException("The bridge has not announced a ventilation unit")

        # pylint: disable=no-member
        return self._send(
            zehnder_pb2.CnRmiRequest,
            zehnder_pb2.GatewayOperation.CnRmiRequestType,
            {"nodeId": node_id, "message": message},
        )

    def cmd_rpdo_request(self, pdid: int, pdo_type: int = 1, zone: int = 1, timeout=None) -> Awaitable[Message]:
        """Register a RPDO request."""
        _LOGGER.debug("CnRpdoRequest")
        # pylint: disable=no-member
        return self._send(
            zehnder_pb2.CnRpdoRequest,
            zehnder_pb2.GatewayOperation.CnRpdoRequestType,
            {"pdid": pdid, "type": pdo_type, "zone": zone or 1, "timeout": timeout},
        )

    def cmd_keepalive(self) -> Awaitable[Message]:
        """Sends a keepalive."""
        _LOGGER.debug("KeepAlive")
        # pylint: disable=no-member
        return self._send(
            zehnder_pb2.KeepAlive,
            zehnder_pb2.GatewayOperation.KeepAliveType,
            reply=False,  # Don't wait for a reply
        )


class Message:
    """A message that is sent to the bridge."""

    # pylint: disable=no-member
    REQUEST_MAPPING = {
        zehnder_pb2.GatewayOperation.SetAddressRequestType: zehnder_pb2.SetAddressRequest,
        zehnder_pb2.GatewayOperation.RegisterAppRequestType: zehnder_pb2.RegisterAppRequest,
        zehnder_pb2.GatewayOperation.StartSessionRequestType: zehnder_pb2.StartSessionRequest,
        zehnder_pb2.GatewayOperation.CloseSessionRequestType: zehnder_pb2.CloseSessionRequest,
        zehnder_pb2.GatewayOperation.ListRegisteredAppsRequestType: zehnder_pb2.ListRegisteredAppsRequest,
        zehnder_pb2.GatewayOperation.DeregisterAppRequestType: zehnder_pb2.DeregisterAppRequest,
        zehnder_pb2.GatewayOperation.ChangePinRequestType: zehnder_pb2.ChangePinRequest,
        zehnder_pb2.GatewayOperation.GetRemoteAccessIdRequestType: zehnder_pb2.GetRemoteAccessIdRequest,
        zehnder_pb2.GatewayOperation.SetRemoteAccessIdRequestType: zehnder_pb2.SetRemoteAccessIdRequest,
        zehnder_pb2.GatewayOperation.GetSupportIdRequestType: zehnder_pb2.GetSupportIdRequest,
        zehnder_pb2.GatewayOperation.SetSupportIdRequestType: zehnder_pb2.SetSupportIdRequest,
        zehnder_pb2.GatewayOperation.GetWebIdRequestType: zehnder_pb2.GetWebIdRequest,
        zehnder_pb2.GatewayOperation.SetWebIdRequestType: zehnder_pb2.SetWebIdRequest,
        zehnder_pb2.GatewayOperation.SetPushIdRequestType: zehnder_pb2.SetPushIdRequest,
        zehnder_pb2.GatewayOperation.DebugRequestType: zehnder_pb2.DebugRequest,
        zehnder_pb2.GatewayOperation.UpgradeRequestType: zehnder_pb2.UpgradeRequest,
        zehnder_pb2.GatewayOperation.SetDeviceSettingsRequestType: zehnder_pb2.SetDeviceSettingsRequest,
        zehnder_pb2.GatewayOperation.VersionRequestType: zehnder_pb2.VersionRequest,
        zehnder_pb2.GatewayOperation.SetAddressConfirmType: zehnder_pb2.SetAddressConfirm,
        zehnder_pb2.GatewayOperation.RegisterAppConfirmType: zehnder_pb2.RegisterAppConfirm,
        zehnder_pb2.GatewayOperation.StartSessionConfirmType: zehnder_pb2.StartSessionConfirm,
        zehnder_pb2.GatewayOperation.CloseSessionConfirmType: zehnder_pb2.CloseSessionConfirm,
        zehnder_pb2.GatewayOperation.ListRegisteredAppsConfirmType: zehnder_pb2.ListRegisteredAppsConfirm,
        zehnder_pb2.GatewayOperation.DeregisterAppConfirmType: zehnder_pb2.DeregisterAppConfirm,
        zehnder_pb2.GatewayOperation.ChangePinConfirmType: zehnder_pb2.ChangePinConfirm,
        zehnder_pb2.GatewayOperation.GetRemoteAccessIdConfirmType: zehnder_pb2.GetRemoteAccessIdConfirm,
        zehnder_pb2.GatewayOperation.SetRemoteAccessIdConfirmType: zehnder_pb2.SetRemoteAccessIdConfirm,
        zehnder_pb2.GatewayOperation.GetSupportIdConfirmType: zehnder_pb2.GetSupportIdConfirm,
        zehnder_pb2.GatewayOperation.SetSupportIdConfirmType: zehnder_pb2.SetSupportIdConfirm,
        zehnder_pb2.GatewayOperation.GetWebIdConfirmType: zehnder_pb2.GetWebIdConfirm,
        zehnder_pb2.GatewayOperation.SetWebIdConfirmType: zehnder_pb2.SetWebIdConfirm,
        zehnder_pb2.GatewayOperation.SetPushIdConfirmType: zehnder_pb2.SetPushIdConfirm,
        zehnder_pb2.GatewayOperation.DebugConfirmType: zehnder_pb2.DebugConfirm,
        zehnder_pb2.GatewayOperation.UpgradeConfirmType: zehnder_pb2.UpgradeConfirm,
        zehnder_pb2.GatewayOperation.SetDeviceSettingsConfirmType: zehnder_pb2.SetDeviceSettingsConfirm,
        zehnder_pb2.GatewayOperation.VersionConfirmType: zehnder_pb2.VersionConfirm,
        zehnder_pb2.GatewayOperation.GatewayNotificationType: zehnder_pb2.GatewayNotification,
        zehnder_pb2.GatewayOperation.KeepAliveType: zehnder_pb2.KeepAlive,
        zehnder_pb2.GatewayOperation.FactoryResetType: zehnder_pb2.FactoryReset,
        zehnder_pb2.GatewayOperation.CnTimeRequestType: zehnder_pb2.CnTimeRequest,
        zehnder_pb2.GatewayOperation.CnTimeConfirmType: zehnder_pb2.CnTimeConfirm,
        zehnder_pb2.GatewayOperation.CnNodeRequestType: zehnder_pb2.CnNodeRequest,
        zehnder_pb2.GatewayOperation.CnNodeNotificationType: zehnder_pb2.CnNodeNotification,
        zehnder_pb2.GatewayOperation.CnRmiRequestType: zehnder_pb2.CnRmiRequest,
        zehnder_pb2.GatewayOperation.CnRmiResponseType: zehnder_pb2.CnRmiResponse,
        zehnder_pb2.GatewayOperation.CnRmiAsyncRequestType: zehnder_pb2.CnRmiAsyncRequest,
        zehnder_pb2.GatewayOperation.CnRmiAsyncConfirmType: zehnder_pb2.CnRmiAsyncConfirm,
        zehnder_pb2.GatewayOperation.CnRmiAsyncResponseType: zehnder_pb2.CnRmiAsyncResponse,
        zehnder_pb2.GatewayOperation.CnRpdoRequestType: zehnder_pb2.CnRpdoRequest,
        zehnder_pb2.GatewayOperation.CnRpdoConfirmType: zehnder_pb2.CnRpdoConfirm,
        zehnder_pb2.GatewayOperation.CnRpdoNotificationType: zehnder_pb2.CnRpdoNotification,
        zehnder_pb2.GatewayOperation.CnAlarmNotificationType: zehnder_pb2.CnAlarmNotification,
        zehnder_pb2.GatewayOperation.CnFupReadRegisterRequestType: zehnder_pb2.CnFupReadRegisterRequest,
        zehnder_pb2.GatewayOperation.CnFupReadRegisterConfirmType: zehnder_pb2.CnFupReadRegisterConfirm,
        zehnder_pb2.GatewayOperation.CnFupProgramBeginRequestType: zehnder_pb2.CnFupProgramBeginRequest,
        zehnder_pb2.GatewayOperation.CnFupProgramBeginConfirmType: zehnder_pb2.CnFupProgramBeginConfirm,
        zehnder_pb2.GatewayOperation.CnFupProgramRequestType: zehnder_pb2.CnFupProgramRequest,
        zehnder_pb2.GatewayOperation.CnFupProgramConfirmType: zehnder_pb2.CnFupProgramConfirm,
        zehnder_pb2.GatewayOperation.CnFupProgramEndRequestType: zehnder_pb2.CnFupProgramEndRequest,
        zehnder_pb2.GatewayOperation.CnFupProgramEndConfirmType: zehnder_pb2.CnFupProgramEndConfirm,
        zehnder_pb2.GatewayOperation.CnFupReadRequestType: zehnder_pb2.CnFupReadRequest,
        zehnder_pb2.GatewayOperation.CnFupReadConfirmType: zehnder_pb2.CnFupReadConfirm,
        zehnder_pb2.GatewayOperation.CnFupResetRequestType: zehnder_pb2.CnFupResetRequest,
        zehnder_pb2.GatewayOperation.CnFupResetConfirmType: zehnder_pb2.CnFupResetConfirm,
    }

    def __init__(self, cmd, msg, src, dst):
        self.cmd: ProtobufMessage = cmd
        self.msg: ProtobufMessage = msg
        self.src: str = src
        self.dst: str = dst

    def __str__(self):
        return f"{self.src} -> {self.dst}: {self.cmd.SerializeToString().hex()} {self.msg.SerializeToString().hex()}\n{self.cmd}\n{self.msg}"

    def encode(self) -> bytes:
        """Encode the message into a byte array"""
        cmd_buf = self.cmd.SerializeToString()
        msg_buf = self.msg.SerializeToString()
        cmd_len_buf = struct.pack(">H", len(cmd_buf))
        msg_len_buf = struct.pack(">L", 16 + 16 + 2 + len(cmd_buf) + len(msg_buf))

        return msg_len_buf + bytes.fromhex(self.src) + bytes.fromhex(self.dst) + cmd_len_buf + cmd_buf + msg_buf

    @classmethod
    def decode(cls, packet) -> Message:
        """Decode a packet from a byte buffer"""
        src_buf = packet[0:16]
        dst_buf = packet[16:32]
        cmd_len = struct.unpack(">H", packet[32:34])[0]
        cmd_buf = packet[34 : 34 + cmd_len]
        msg_buf = packet[34 + cmd_len :]

        # Parse command
        cmd = zehnder_pb2.GatewayOperation()
        cmd.ParseFromString(cmd_buf)

        # Parse message
        cmd_type = cls.REQUEST_MAPPING.get(cmd.type)
        msg = cmd_type()
        msg.ParseFromString(msg_buf)

        return Message(cmd, msg, src_buf.hex(), dst_buf.hex())
