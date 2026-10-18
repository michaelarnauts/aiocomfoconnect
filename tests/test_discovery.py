"""Tests for the bridge discovery."""

import asyncio
import inspect
from ipaddress import IPv4Address
from unittest.mock import MagicMock, patch

import pytest

from aiocomfoconnect import discovery
from aiocomfoconnect.bridge import Bridge
from aiocomfoconnect.discovery import BROADCAST_ADDRESS, BridgeDiscoveryProtocol, discover_bridges
from aiocomfoconnect.protobuf import zehnder_pb2

BRIDGE_UUID = "0000000000221111111111111111ffff"


def discovery_response(host: str = "192.168.1.213", uuid: str = BRIDGE_UUID, gateway_type: int = 0) -> bytes:
    """Build a discovery response, like a bridge would send."""
    operation = zehnder_pb2.DiscoveryOperation()  # pylint: disable=no-member
    operation.searchGatewayResponse.ipaddress = host
    operation.searchGatewayResponse.uuid = bytes.fromhex(uuid)
    operation.searchGatewayResponse.version = 1
    operation.searchGatewayResponse.type = gateway_type

    return operation.SerializeToString()


def targets_of(protocol: BridgeDiscoveryProtocol) -> list:
    """Connect a mocked transport and return the addresses that were sent to."""
    transport = MagicMock()
    protocol.connection_made(transport)

    return [call.args[1][0] for call in transport.sendto.call_args_list]


class TestBridgeDiscoveryProtocol:
    """Test the BridgeDiscoveryProtocol class."""

    @pytest.mark.asyncio
    async def test_broadcasts_to_limited_broadcast_by_default(self):
        """Test that we keep broadcasting to the limited broadcast address when nothing is passed."""
        protocol = BridgeDiscoveryProtocol()

        assert targets_of(protocol) == [BROADCAST_ADDRESS]

    @pytest.mark.asyncio
    async def test_broadcasts_to_every_broadcast_address(self):
        """Test that every broadcast address we know about is searched."""
        protocol = BridgeDiscoveryProtocol(broadcast_addresses=["192.168.1.255", "10.0.0.255"])

        assert targets_of(protocol) == ["192.168.1.255", "10.0.0.255"]

    @pytest.mark.asyncio
    async def test_accepts_ipaddress_objects(self):
        """Test that we accept the IPv4Address objects that Home Assistant hands out."""
        protocol = BridgeDiscoveryProtocol(broadcast_addresses=[IPv4Address("192.168.1.255")])

        assert targets_of(protocol) == ["192.168.1.255"]

    @pytest.mark.asyncio
    async def test_host_takes_precedence(self):
        """Test that we only send to the host when one is passed."""
        protocol = BridgeDiscoveryProtocol(target="192.168.1.213", broadcast_addresses=["192.168.1.255"])

        assert targets_of(protocol) == ["192.168.1.213"]

    @pytest.mark.asyncio
    async def test_bridge_is_reported_once(self):
        """Test that a bridge that replies to multiple requests is only reported once."""
        protocol = BridgeDiscoveryProtocol(broadcast_addresses=["192.168.1.255", "255.255.255.255"])
        targets_of(protocol)

        protocol.datagram_received(discovery_response(), ("192.168.1.213", Bridge.PORT))
        protocol.datagram_received(discovery_response(), ("192.168.1.213", Bridge.PORT))
        protocol.disconnect()

        bridges = await protocol.get_bridges()
        assert len(bridges) == 1
        assert bridges[0].host == "192.168.1.213"
        assert bridges[0].uuid == BRIDGE_UUID

    @pytest.mark.asyncio
    async def test_multiple_bridges_are_reported(self):
        """Test that bridges on different networks are all reported."""
        protocol = BridgeDiscoveryProtocol(broadcast_addresses=["192.168.1.255", "10.0.0.255"])
        targets_of(protocol)

        protocol.datagram_received(discovery_response(host="192.168.1.213"), ("192.168.1.213", Bridge.PORT))
        protocol.datagram_received(discovery_response(host="10.0.0.213", uuid="0000000000222222222222222222ffff"), ("10.0.0.213", Bridge.PORT))
        protocol.disconnect()

        bridges = await protocol.get_bridges()
        assert [bridge.host for bridge in bridges] == ["192.168.1.213", "10.0.0.213"]

    @pytest.mark.asyncio
    async def test_disconnect_is_idempotent(self):
        """Test that a late response after the timeout doesn't blow up on the completed future."""
        protocol = BridgeDiscoveryProtocol(target="192.168.1.213")
        targets_of(protocol)

        protocol.disconnect()  # The timeout expires.
        protocol.datagram_received(discovery_response(), ("192.168.1.213", Bridge.PORT))  # Disconnects a second time.

        assert await protocol.get_bridges() == []

    @pytest.mark.asyncio
    async def test_discovery_request_is_ignored(self):
        """Test that we ignore the discovery requests of other clients."""
        protocol = BridgeDiscoveryProtocol()
        targets_of(protocol)

        protocol.datagram_received(b"\x0a\x00", ("192.168.1.10", Bridge.PORT))
        protocol.disconnect()

        assert await protocol.get_bridges() == []

    @pytest.mark.asyncio
    @pytest.mark.parametrize("data", [b"\xff\xff\xff", b"", b"\x12\x00"])
    async def test_invalid_datagram_is_ignored(self, data, caplog):
        """Test that a datagram that isn't a valid discovery response is skipped without an error."""
        protocol = BridgeDiscoveryProtocol()
        targets_of(protocol)

        protocol.datagram_received(data, ("192.168.1.10", Bridge.PORT))
        protocol.datagram_received(discovery_response(), ("192.168.1.213", Bridge.PORT))
        protocol.disconnect()

        assert [bridge.host for bridge in await protocol.get_bridges()] == ["192.168.1.213"]
        assert not [record for record in caplog.records if record.levelname == "ERROR"]


class FakeDiscoveryResponder(asyncio.DatagramProtocol):
    """A bridge on a local UDP socket that answers discovery requests, unless it is told to stay silent."""

    def __init__(self, silent: bool = False):
        self.silent = silent
        self.transport = None

    def connection_made(self, transport):
        self.transport = transport

    def datagram_received(self, data, addr):
        if not self.silent and data == b"\x0a\x00":
            self.transport.sendto(discovery_response(host="127.0.0.1"), addr)


@pytest.fixture
async def responder(monkeypatch):
    """Start a fake bridge on localhost and point the discovery at its port."""
    transport, protocol = await asyncio.get_running_loop().create_datagram_endpoint(FakeDiscoveryResponder, local_addr=("127.0.0.1", 0))
    monkeypatch.setattr(Bridge, "PORT", transport.get_extra_info("sockname")[1])
    yield protocol
    transport.close()


@pytest.fixture
def transports():
    """Record the transports that the discovery opens."""
    opened = []

    class RecordingProtocol(BridgeDiscoveryProtocol):
        """Remembers its transport."""

        def connection_made(self, transport):
            opened.append(transport)
            super().connection_made(transport)

    with patch.object(discovery, "BridgeDiscoveryProtocol", RecordingProtocol):
        yield opened


class TestDiscoverBridges:
    """Test discover_bridges against a fake bridge on a local UDP socket."""

    async def test_discovers_host(self, responder, transports):
        """The bridge that answers is returned right away, and the socket is closed."""
        bridges = await asyncio.wait_for(discover_bridges("127.0.0.1", timeout=10), 2)

        assert [(bridge.host, bridge.uuid) for bridge in bridges] == [("127.0.0.1", BRIDGE_UUID)]
        assert len(transports) == 1 and transports[0].is_closing()

    async def test_no_answer_times_out(self, responder, transports):
        """Nothing is returned when the bridge doesn't answer, and the socket is closed."""
        responder.silent = True

        assert await discover_bridges("127.0.0.1", timeout=0.1) == []
        assert len(transports) == 1 and transports[0].is_closing()

    async def test_cancel_closes_the_socket(self, responder, transports):
        """The socket is closed when the discovery is cancelled."""
        responder.silent = True
        task = asyncio.create_task(discover_bridges("127.0.0.1", timeout=10))
        await asyncio.sleep(0.05)
        task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await task
        assert len(transports) == 1 and transports[0].is_closing()

    def test_default_timeout(self):
        """The discovery waits one second by default."""
        assert inspect.signature(discover_bridges).parameters["timeout"].default == 1
