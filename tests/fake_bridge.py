"""A fake ComfoConnect bridge on localhost that speaks the real protocol, for tests.

It answers the requests the library sends while connecting and talking to the ventilation unit, records everything it
receives, and lets a test push notifications, drop the connection or make the bridge go silent.
"""

from __future__ import annotations

import asyncio
from asyncio import StreamReader, StreamWriter
from typing import Callable, Dict, List, Optional, Set, Tuple, Union

from aiocomfoconnect.bridge import Message
from aiocomfoconnect.const import ProductId
from aiocomfoconnect.protobuf import zehnder_pb2 as pb

GO = pb.GatewayOperation  # pylint: disable=no-member

BRIDGE_UUID = "00000000000000000000000000000b1d"
LOCAL_UUID = "00000000000000000000000000000001"

# The reply type of the requests that a bridge answers with NOT_ALLOWED when it has dropped our session.
LOST_SESSION_REPLIES = {
    GO.CnRmiRequestType: GO.CnRmiResponseType,
    GO.CnRpdoRequestType: GO.CnRpdoConfirmType,
    GO.CnTimeRequestType: GO.CnTimeConfirmType,
}


class FakeBridge:
    """A ComfoConnect LAN C on 127.0.0.1, on a free port."""

    def __init__(self):
        # The nodes announced on a CnNodeRequest, as (node_id, product_id, zone_id).
        self.nodes: List[Tuple[int, int, int]] = [(1, ProductId.COMFOAIRQ, 1)]
        # The result code of a StartSessionRequest, e.g. GO.NOT_ALLOWED for an app that isn't registered.
        self.session_result: int = GO.OK
        # The result code of a CnRpdoRequest per pdid, OK when not listed.
        self.rpdo_results: Dict[int, int] = {}
        # The response per RMI request: the response bytes, or a result code like GO.RMI_ERROR. Others get an empty response.
        self.rmi_responses: Dict[bytes, Union[bytes, int]] = {}
        # When silent, requests are recorded but never answered, like a bridge that hangs.
        self.silent = False
        # Request types that are recorded but only answered when the test calls answer_pending().
        self.withhold: Set[int] = set()
        # Connections whose session the bridge has dropped without closing them: every request on them gets NOT_ALLOWED.
        self.lost_sessions: Set[int] = set()

        # Everything we received, as (connection number, message). Connections are numbered from 1.
        self.requests: List[Tuple[int, Message]] = []
        self.connections = 0
        self._pending: List[Tuple[StreamWriter, Message]] = []
        self._writers: List[StreamWriter] = []
        self._server: Optional[asyncio.Server] = None
        self.port: Optional[int] = None

    async def __aenter__(self) -> FakeBridge:
        self._server = await asyncio.start_server(self._handle, "127.0.0.1", 0)
        self.port = self._server.sockets[0].getsockname()[1]
        return self

    async def __aexit__(self, *exc):
        for writer in self._writers:
            writer.close()
        self._server.close()
        await self._server.wait_closed()

    async def _handle(self, reader: StreamReader, writer: StreamWriter):
        self.connections += 1
        connection = self.connections
        self._writers.append(writer)
        try:
            while True:
                length = int.from_bytes(await reader.readexactly(4), byteorder="big")
                message = Message.decode(await reader.readexactly(length))
                self.requests.append((connection, message))
                if self.silent or message.cmd.type in self.withhold:
                    self._pending.append((writer, message))
                else:
                    self._answer(writer, message)
                await writer.drain()
        except (asyncio.IncompleteReadError, ConnectionError):
            pass
        finally:
            writer.close()

    def _answer(self, writer: StreamWriter, request: Message):
        """Answer a request like a real bridge does."""
        msg = request.msg
        lost = self._writers.index(writer) + 1 in self.lost_sessions
        if lost and request.cmd.type in LOST_SESSION_REPLIES:
            self._send(writer, LOST_SESSION_REPLIES[request.cmd.type], pb.CnRmiResponse(), request.cmd.reference, GO.NOT_ALLOWED)
        elif request.cmd.type == GO.StartSessionRequestType:
            self._send(writer, GO.StartSessionConfirmType, pb.StartSessionConfirm(), request.cmd.reference, self.session_result)
        elif request.cmd.type == GO.CnNodeRequestType:
            for node_id, product_id, zone_id in self.nodes:
                self.send_node(node_id, product_id, zone_id, writer=writer)
        elif request.cmd.type == GO.CnRpdoRequestType:
            self._send(writer, GO.CnRpdoConfirmType, pb.CnRpdoConfirm(), request.cmd.reference, self.rpdo_results.get(msg.pdid, GO.OK))
        elif request.cmd.type == GO.CnRmiRequestType:
            response = self.rmi_responses.get(bytes(msg.message), b"")
            if isinstance(response, int):
                self._send(writer, GO.CnRmiResponseType, pb.CnRmiResponse(), request.cmd.reference, response)
            else:
                self._send(writer, GO.CnRmiResponseType, pb.CnRmiResponse(message=response), request.cmd.reference)
        elif request.cmd.type == GO.CnTimeRequestType:
            self._send(writer, GO.CnTimeConfirmType, pb.CnTimeConfirm(currentTime=1), request.cmd.reference)
        elif request.cmd.type == GO.CloseSessionRequestType:
            writer.close()  # The bridge ends the session by closing the connection.

    def answer_pending(self):
        """Answer the requests that were withheld or received while silent."""
        pending, self._pending = self._pending, []
        for writer, request in pending:
            self._answer(writer, request)

    @staticmethod
    def _send(writer: StreamWriter, op_type: int, msg, reference: int = 0, result: int = GO.OK):
        cmd = GO(type=op_type, reference=reference, result=result)
        writer.write(Message(cmd, msg, BRIDGE_UUID, LOCAL_UUID).encode())

    def send(self, op_type: int, msg, writer: Optional[StreamWriter] = None):
        """Send a message to the client on the last connection."""
        self._send(writer or self._writers[-1], op_type, msg)

    def send_node(self, node_id: int, product_id: int, zone_id: int = 1, mode: int = pb.CnNodeNotification.NODE_NORMAL, writer=None):
        """Announce a node."""
        self.send(GO.CnNodeNotificationType, pb.CnNodeNotification(nodeId=node_id, productId=product_id, zoneId=zone_id, mode=mode), writer)

    def push_sensor(self, pdid: int, data: bytes):
        """Send a sensor value, like the bridge does for a subscribed sensor."""
        self.send(GO.CnRpdoNotificationType, pb.CnRpdoNotification(pdid=pdid, data=data))

    def push_alarm(self, node_id: int, errors: bytes, sw_version: int = 3222278145):
        """Send an alarm notification."""
        self.send(GO.CnAlarmNotificationType, pb.CnAlarmNotification(nodeId=node_id, swProgramVersion=sw_version, errors=errors))

    def close_session(self):
        """Ask the client to close the session, like the bridge does when another app takes over."""
        self.send(GO.CloseSessionRequestType, pb.CloseSessionRequest())

    def drop(self):
        """Drop the last connection."""
        self._writers[-1].close()

    def received(self, op_type: int, connection: Optional[int] = None) -> list:
        """The messages of a request type that we received, optionally only on the given connection."""
        return [message.msg for conn, message in self.requests if message.cmd.type == op_type and connection in (None, conn)]

    @property
    def rmi_requests(self) -> List[bytes]:
        """The bytes of the RMI requests that we received."""
        return [bytes(msg.message) for msg in self.received(GO.CnRmiRequestType)]

    @staticmethod
    async def wait_for(predicate: Callable[[], bool], timeout: float = 2):
        """Wait until the predicate is true, e.g. until a request arrived or the client reconnected."""
        async with asyncio.timeout(timeout):
            while not predicate():
                await asyncio.sleep(0.001)
