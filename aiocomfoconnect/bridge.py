""" ComfoConnect LAN C API. """
from __future__ import annotations

import asyncio
import logging
import struct
from asyncio import IncompleteReadError, StreamReader, StreamWriter

from google.protobuf.message import DecodeError
from google.protobuf.message import Message as ProtobufMessage

from .exceptions import *
from .protobuf import zehnder_pb2

_LOGGER = logging.getLogger(__name__)


class EventBus:
    """An event bus for async replies."""

    def __init__(self):
        self.listeners = {}

    def add_listener(self, event_name, future):
        _LOGGER.debug("Adding listener for event %s", event_name)
        if not self.listeners.get(event_name, None):
            self.listeners[event_name] = {future}
        else:
            self.listeners[event_name].add(future)

    def emit(self, event_name, event):
        _LOGGER.debug("Emitting for event %s", event_name)
        futures = self.listeners.get(event_name, [])
        for future in futures:
            if isinstance(event, Exception):
                future.set_exception(event)
            else:
                future.set_result(event)
        del self.listeners[event_name]


class Bridge:
    """ComfoConnect LAN C API."""

    PORT = 56747

    def __init__(self, host: str, uuid: str, loop=None):
        self.host: str = host
        self.uuid: str = uuid
        self._local_uuid: str = None

        self._reader: StreamReader = None
        self._writer: StreamWriter = None
        self._reference = None

        self._event_bus: EventBus = None
        self._read_task: asyncio.Task = None

        self.__sensor_callback_fn: callable = None
        self.__alarm_callback_fn: callable = None

        self._loop = loop or asyncio.get_running_loop()

    def __repr__(self):
        return "<Bridge {0}, UID={1}>".format(self.host, self.uuid)

    def set_sensor_callback(self, callback: callable):
        """Set a callback to be called when a message is received."""
        self.__sensor_callback_fn = callback

    def set_alarm_callback(self, callback: callable):
        """Set a callback to be called when an alarm is received."""
        self.__alarm_callback_fn = callback

    async def connect(self, uuid: str):
        """Connect to the bridge."""
        _LOGGER.debug("Connecting to bridge %s", self.host)
        self._reader, self._writer = await asyncio.open_connection(self.host, self.PORT)
        self._reference = 1
        self._local_uuid = uuid
        self._event_bus = EventBus()

        # We are connected, start the background task
        self._read_task = self._loop.create_task(self._read_messages())

    async def disconnect(self):
        """Disconnect from the bridge."""
        _LOGGER.debug("Disconnecting from bridge %s", self.host)

        # Cancel the background task
        self._read_task.cancel()

        # Disconnect
        await self.cmd_close_session()

        # Wait for background task to finish
        try:
            await self._read_task
        except asyncio.CancelledError:
            pass

    def is_connected(self) -> bool:
        """Returns True if the bridge is connected."""
        return self._writer is not None and not self._writer.is_closing()

    def _send(self, request, request_type, params: dict = None, reply: bool = True):
        """Sends a command and wait for a response if the request is known to return a result."""
        # Check if we are actually connected
        if not self.is_connected():
            raise AioComfoConnectNotConnected()

        # Construct the message
        cmd = zehnder_pb2.GatewayOperation()
        cmd.type = request_type
        cmd.reference = self._reference

        msg = request()
        if params is not None:
            for param in params:
                if params[param] is not None:
                    setattr(msg, param, params[param])

        message = Message(cmd, msg, self._local_uuid, self.uuid)

        # Create the future that will contain the response
        fut = asyncio.Future()
        if reply:
            self._event_bus.add_listener(self._reference, fut)
        else:
            fut.set_result(None)

        # Send the message
        _LOGGER.debug("TX %s", message)
        self._writer.write(message.encode())

        # Increase message reference for next message
        self._reference += 1

        return fut

    async def _read(self):
        # Read packet size
        msg_len_buf = await self._reader.readexactly(4)

        # Read rest of packet
        msg_len = int.from_bytes(msg_len_buf, byteorder="big")
        msg_buf = await self._reader.readexactly(msg_len)

        # Decode message
        message = Message.decode(msg_buf)

        _LOGGER.debug("RX %s", message)

        # Check status code
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

    async def _read_messages(self):
        """Receive a message from the bridge."""
        while self._read_task.cancelled() is False:
            try:
                message = await self._read()

                if message.cmd.type == zehnder_pb2.GatewayOperation.CnRpdoNotificationType:
                    if self.__sensor_callback_fn:
                        self.__sensor_callback_fn(message.msg.pdid, int.from_bytes(message.msg.data, byteorder="little", signed=True))
                    else:
                        _LOGGER.info("Unhandled CnRpdoNotificationType since no callback is registered.")

                elif message.cmd.type == zehnder_pb2.GatewayOperation.GatewayNotificationType:
                    _LOGGER.info("Unhandled GatewayNotificationType")
                    # TODO: We should probably handle these somehow

                elif message.cmd.type == zehnder_pb2.GatewayOperation.CnNodeNotificationType:
                    _LOGGER.info("Unhandled CnNodeNotificationType")
                    # TODO: We should probably handle these somehow

                elif message.cmd.type == zehnder_pb2.GatewayOperation.CnAlarmNotificationType:
                    if self.__alarm_callback_fn:
                        self.__alarm_callback_fn(message.msg.nodeId, message.msg)
                    else:
                        _LOGGER.info("Unhandled CnAlarmNotificationType since no callback is registered.")

                elif message.cmd.type == zehnder_pb2.GatewayOperation.CloseSessionRequestType:
                    _LOGGER.info("The Bridge has asked us to close the connection.")
                    return  # Stop the background task

                elif message.cmd.reference:
                    # Emit to the event bus
                    self._event_bus.emit(message.cmd.reference, message.msg)

                else:
                    _LOGGER.error("Unhandled message type %s: %s", message.cmd.type, message)

            except asyncio.exceptions.CancelledError:
                return  # Stop the background task

            except IncompleteReadError:
                _LOGGER.info("The connection was closed.")
                return  # Stop the background task

            except ComfoConnectError as exc:
                if exc.message.cmd.reference:
                    self._event_bus.emit(exc.message.cmd.reference, exc)

            except DecodeError as exc:
                _LOGGER.error("Failed to decode message: %s", exc)

    def cmd_start_session(self, take_over: bool = False):
        """Starts the session on the device by logging in and optionally disconnecting an already existing session."""
        _LOGGER.debug("StartSessionRequest")
        result = self._send(
            zehnder_pb2.StartSessionRequest,
            zehnder_pb2.GatewayOperation.StartSessionRequestType,
            {"takeover": take_over},
        )
        return result

    def cmd_close_session(self):
        """Stops the current session."""
        _LOGGER.debug("CloseSessionRequest")
        result = self._send(
            zehnder_pb2.CloseSessionRequest,
            zehnder_pb2.GatewayOperation.CloseSessionRequestType,
            reply=False,  # Don't wait for a reply
        )
        return result

    def cmd_list_registered_apps(self):
        """Returns a list of all the registered clients."""
        _LOGGER.debug("ListRegisteredAppsRequest")
        return self._send(
            zehnder_pb2.ListRegisteredAppsRequest,
            zehnder_pb2.GatewayOperation.ListRegisteredAppsRequestType,
        )

    def cmd_register_app(self, uuid: str, device_name: str, pin: int):
        """Register a new app by specifying our own uuid, device_name and pin code."""
        _LOGGER.debug("RegisterAppRequest")
        return self._send(
            zehnder_pb2.RegisterAppRequest,
            zehnder_pb2.GatewayOperation.RegisterAppRequestType,
            {
                "uuid": bytes.fromhex(uuid),
                "devicename": device_name,
                "pin": int(pin),
            },
        )

    def cmd_deregister_app(self, uuid: str):
        """Remove the specified app from the registration list."""
        _LOGGER.debug("DeregisterAppRequest")
        if uuid == self._local_uuid:
            raise Exception("You should not deregister yourself.")

        return self._send(
            zehnder_pb2.DeregisterAppRequest,
            zehnder_pb2.GatewayOperation.DeregisterAppRequestType,
            {"uuid": bytes.fromhex(uuid)},
        )

    def cmd_version_request(self):
        """Returns version information."""
        _LOGGER.debug("VersionRequest")
        return self._send(
            zehnder_pb2.VersionRequest,
            zehnder_pb2.GatewayOperation.VersionRequestType,
        )

    def cmd_time_request(self):
        """Returns the current time on the device."""
        _LOGGER.debug("CnTimeRequest")
        return self._send(
            zehnder_pb2.CnTimeRequest,
            zehnder_pb2.GatewayOperation.CnTimeRequestType,
        )

    def cmd_rmi_request(self, message, node_id: int = 1):
        """Sends a RMI request."""
        _LOGGER.debug("CnRmiRequest")
        return self._send(
            zehnder_pb2.CnRmiRequest,
            zehnder_pb2.GatewayOperation.CnRmiRequestType,
            {"nodeId": node_id or 1, "message": message},
        )

    def cmd_rpdo_request(self, pdid: int, type: int = 1, zone: int = 1, timeout=None):
        """Register a RPDO request."""
        _LOGGER.debug("CnRpdoRequest")
        return self._send(
            zehnder_pb2.CnRpdoRequest,
            zehnder_pb2.GatewayOperation.CnRpdoRequestType,
            {"pdid": pdid, "type": type, "zone": zone or 1, "timeout": timeout},
        )

    def cmd_keepalive(self):
        """Sends a keepalive."""
        _LOGGER.debug("KeepAlive")
        return self._send(
            zehnder_pb2.KeepAlive,
            zehnder_pb2.GatewayOperation.KeepAliveType,
            reply=False,  # Don't wait for a reply
        )


class Message(object):
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
        return "%s -> %s: %s %s\n%s\n%s" % (
            self.src,
            self.dst,
            self.cmd.SerializeToString().hex(),
            self.msg.SerializeToString().hex(),
            self.cmd,
            self.msg,
        )

    def encode(self):
        cmd_buf = self.cmd.SerializeToString()
        msg_buf = self.msg.SerializeToString()
        cmd_len_buf = struct.pack(">H", len(cmd_buf))
        msg_len_buf = struct.pack(">L", 16 + 16 + 2 + len(cmd_buf) + len(msg_buf))

        return msg_len_buf + bytes.fromhex(self.src) + bytes.fromhex(self.dst) + cmd_len_buf + cmd_buf + msg_buf

    @classmethod
    def decode(cls, packet):
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
