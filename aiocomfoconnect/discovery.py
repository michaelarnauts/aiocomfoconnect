""" Bridge discovery """

from __future__ import annotations

import asyncio
import logging
from typing import Any, List, Union

import netifaces

from .bridge import Bridge
from .protobuf import zehnder_pb2

_LOGGER = logging.getLogger(__name__)


class BridgeDiscoveryProtocol(asyncio.DatagramProtocol):
    """UDP Protocol for the ComfoConnect LAN C bridge discovery."""

    def __init__(self, target: str | None = None, timeout: int = 5):
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
            # Determine broadcast address programmatically
            try:
                gws = netifaces.gateways()
                default_iface = gws['default'][netifaces.AF_INET][1]
                addrs = netifaces.ifaddresses(default_iface)
                broadcast_addr = addrs[netifaces.AF_INET][0].get('broadcast', '255.255.255.255')
            except Exception as e:
                _LOGGER.warning("Could not determine broadcast address, using 255.255.255.255: %s", e)
                broadcast_addr = '255.255.255.255'
            _LOGGER.debug("Sending discovery request to broadcast:%d (%s)", Bridge.PORT, broadcast_addr)
            self.transport.sendto(b"\x0a\x00", (broadcast_addr, Bridge.PORT))

    def datagram_received(self, data: Union[bytes, str], addr: tuple[str | Any, int]):
        """Called when some datagram is received."""
        if data == b"\x0a\x00":
            _LOGGER.debug("Ignoring discovery request from %s:%d", addr[0], addr[1])
            return

        _LOGGER.debug("Data received from %s: %s", addr, data)
        try:
            # Decode the response
            parser = zehnder_pb2.DiscoveryOperation()  # pylint: disable=no-member
            parser.ParseFromString(data)

            self._bridges.append(Bridge(host=parser.searchGatewayResponse.ipaddress, uuid=parser.searchGatewayResponse.uuid.hex()))
        except Exception as exc:
            _LOGGER.error("Failed to parse discovery response from %s: %s", addr, exc)
            return

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


async def discover_bridges(host: str | None = None, timeout: int = 1, loop=None) -> List[Bridge]:
    """
    Discover ComfoConnect bridges on the local network or at a specified host.

    This asynchronous function sends a UDP broadcast (or unicast if a host is specified)
    to discover available ComfoConnect bridges. It returns a list of discovered Bridge
    instances.

    Args:
        host (str | None): The IP address of a specific bridge to discover. If None,
            a broadcast is sent to discover all available bridges. Defaults to None.
        timeout (int): The time in seconds to wait for responses. Defaults to 1.
        loop (asyncio.AbstractEventLoop, optional): The event loop to use. If None,
            the default event loop is used.

    Returns:
        List[Bridge]: A list of discovered Bridge objects.

    Raises:
        Any exceptions raised by the underlying asyncio transport or protocol.

    Example:
        bridges = await discover_bridges(timeout=2)
    """

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
