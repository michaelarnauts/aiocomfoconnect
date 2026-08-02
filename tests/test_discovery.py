"""Tests for the bridge discovery."""

from ipaddress import IPv4Address
from unittest.mock import MagicMock

import pytest

from aiocomfoconnect.bridge import Bridge
from aiocomfoconnect.discovery import BROADCAST_ADDRESS, BridgeDiscoveryProtocol
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
