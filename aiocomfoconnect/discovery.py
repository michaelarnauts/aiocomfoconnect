""" Bridge discovery """
from __future__ import annotations

import asyncio
import logging
from typing import Any, List, Text, Union

from .bridge import Bridge
from .protobuf import zehnder_pb2

_LOGGER = logging.getLogger(__name__)


class BridgeDiscoveryProtocol(asyncio.DatagramProtocol):
    """UDP Protocol for the ComfoConnect LAN C bridge discovery."""

    def __init__(self, target: str = None, timeout: int = 5):
        loop = asyncio.get_running_loop()

        self._bridges: List[Bridge] = []
        self._target = target
        self._future = loop.create_future()
        self.transport = None
        self._timeout = loop.call_later(timeout, self.disconnect)

    def connection_made(self, transport: asyncio.transports.DatagramTransport):
        """Called when a connection is made."""
        _LOGGER.debug("Socket has been created")
        self.transport = transport

        if self._target:
            _LOGGER.debug("Sending discovery request to %s:%d", self._target, Bridge.PORT)
            self.transport.sendto(b"\x0a\x00", (self._target, Bridge.PORT))
        else:
            _LOGGER.debug("Sending discovery request to broadcast:%d", Bridge.PORT)
            self.transport.sendto(b"\x0a\x00", ("<broadcast>", Bridge.PORT))

    def datagram_received(self, data: Union[bytes, Text], addr: tuple[str | Any, int]):
        """Called when some datagram is received."""
        if data == b"\x0a\x00":
            _LOGGER.debug("Ignoring discovery request from %s:%d", addr[0], addr[1])
            return

        _LOGGER.debug("Data received from %s: %s", addr, data)

        # Decode the response
        parser = zehnder_pb2.DiscoveryOperation()  # pylint: disable=no-member
        parser.ParseFromString(data)

        self._bridges.append(Bridge(host=parser.searchGatewayResponse.ipaddress, uuid=parser.searchGatewayResponse.uuid.hex()))

        # When we have passed a target, we only want to listen for that one
        if self._target:
            self._timeout.cancel()
            self.disconnect()

    def disconnect(self):
        """Disconnect the socket."""
        if self.transport:
            self.transport.close()
        self._future.set_result(self._bridges)

    def get_bridges(self):
        """Return the discovered bridges."""
        return self._future


async def discover_bridges(host: str = None, timeout: int = 1, loop=None) -> List[Bridge]:
    """Discover a bridge by IP."""

    if loop is None:
        loop = asyncio.get_event_loop()

    transport, protocol = await loop.create_datagram_endpoint(
        lambda: BridgeDiscoveryProtocol(host, timeout),
        local_addr=("0.0.0.0", 0),
        allow_broadcast=not host,
    )

    try:
        return await protocol.get_bridges()
    finally:
        transport.close()
