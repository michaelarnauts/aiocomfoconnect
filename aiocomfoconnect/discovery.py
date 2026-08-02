"""Bridge discovery"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Iterable, List, Union

from .bridge import Bridge
from .protobuf import zehnder_pb2

_LOGGER = logging.getLogger(__name__)

# The limited broadcast address. The operating system sends this out over a single interface, the one
# that the routing table selects, so it doesn't reach bridges that live behind another interface.
BROADCAST_ADDRESS = "<broadcast>"


class BridgeDiscoveryProtocol(asyncio.DatagramProtocol):
    """UDP Protocol for the ComfoConnect LAN C bridge discovery."""

    def __init__(self, target: str = None, timeout: int = 5, broadcast_addresses: Iterable[Any] = None):
        loop = asyncio.get_running_loop()

        self._bridges: List[Bridge] = []
        self._bridge_uuids: set[str] = set()
        self._target = target
        self._future = loop.create_future()
        self.transport = None
        self._timeout = loop.call_later(timeout, self.disconnect)

        if target:
            self._targets = [target]
        elif broadcast_addresses:
            # Addresses can be passed as ipaddress objects, since that is what Home Assistant hands out.
            self._targets = [str(address) for address in broadcast_addresses]
        else:
            self._targets = [BROADCAST_ADDRESS]

    def connection_made(self, transport: asyncio.transports.DatagramTransport):
        """Called when a connection is made."""
        _LOGGER.debug("Socket has been created")
        self.transport = transport

        for target in self._targets:
            _LOGGER.debug("Sending discovery request to %s:%d", target, Bridge.PORT)
            self.transport.sendto(b"\x0a\x00", (target, Bridge.PORT))

    def datagram_received(self, data: Union[bytes, str], addr: tuple[str | Any, int]):
        """Called when some datagram is received."""
        if self._future.done():
            _LOGGER.debug("Ignoring data received from %s after the discovery finished", addr)
            return

        if data == b"\x0a\x00":
            _LOGGER.debug("Ignoring discovery request from %s:%d", addr[0], addr[1])
            return

        _LOGGER.debug("Data received from %s: %s", addr, data)

        # Decode the response
        parser = zehnder_pb2.DiscoveryOperation()  # pylint: disable=no-member
        parser.ParseFromString(data)

        uuid = parser.searchGatewayResponse.uuid.hex()

        # A bridge can reply to more than one of our discovery requests.
        if uuid not in self._bridge_uuids:
            self._bridge_uuids.add(uuid)
            self._bridges.append(
                Bridge(
                    host=parser.searchGatewayResponse.ipaddress,
                    uuid=uuid,
                    bridge_type=parser.searchGatewayResponse.type,
                )
            )

        # When we have passed a target, we only want to listen for that one
        if self._target:
            self._timeout.cancel()
            self.disconnect()

    def disconnect(self):
        """Disconnect the socket."""
        if self.transport:
            self.transport.close()
        if not self._future.done():
            self._future.set_result(self._bridges)

    def get_bridges(self):
        """Return the discovered bridges."""
        return self._future


async def discover_bridges(host: str = None, timeout: int = 1, loop=None, broadcast_addresses: Iterable[Any] = None) -> List[Bridge]:
    """Discover bridges on the network, or by IP.

    The discovery request is sent to the limited broadcast address by default, which only reaches the
    interface that the routing table picks. Pass the broadcast address of every network you want to
    search in broadcast_addresses to reach bridges behind the other interfaces as well. In Home
    Assistant, `network.async_get_ipv4_broadcast_addresses()` provides these.
    """

    if loop is None:
        loop = asyncio.get_event_loop()

    transport, protocol = await loop.create_datagram_endpoint(
        lambda: BridgeDiscoveryProtocol(host, timeout, broadcast_addresses),
        local_addr=("0.0.0.0", 0),
        allow_broadcast=not host,
    )

    try:
        bridges = await protocol.get_bridges()
    finally:
        transport.close()

    if not bridges:
        _LOGGER.info("No bridges responded to the discovery request")

    return bridges
