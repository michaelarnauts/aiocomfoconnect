"""Tests for the command line interface."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from aiocomfoconnect import DEFAULT_UUID
from aiocomfoconnect import __main__ as cli
from aiocomfoconnect.bridge import Node
from aiocomfoconnect.comfoconnect import NodeInfo
from aiocomfoconnect.const import ProductId
from aiocomfoconnect.exceptions import ComfoConnectNotAllowed, ComfoConnectRmiError

FAKE_HOST = "192.0.2.1"
FAKE_BRIDGE_UUID = "0000000000000000000000000000beef"
OTHER_UUID = "0000000000000000000000000000cafe"


def parse(*argv):
    """Parse the arguments like the CLI does."""
    return cli.build_parser().parse_args(list(argv))


@pytest.fixture
def bridge():
    """Mock discovery and the ComfoConnect class, and return the mocked ComfoConnect instance."""
    comfoconnect = MagicMock()
    comfoconnect.connect = AsyncMock()
    comfoconnect.disconnect = AsyncMock()
    comfoconnect.register = AsyncMock(return_value=True)
    comfoconnect.register_sensor = AsyncMock()
    comfoconnect.set_speed = AsyncMock()
    comfoconnect.cmd_deregister_app = AsyncMock()
    comfoconnect.cmd_list_registered_apps = AsyncMock(return_value=SimpleNamespace(apps=[]))

    discovered = [SimpleNamespace(host=FAKE_HOST, uuid=FAKE_BRIDGE_UUID, bridge_type=0)]
    with (
        patch.object(cli, "discover_bridges", AsyncMock(return_value=discovered)),
        patch.object(cli, "ComfoConnect", MagicMock(return_value=comfoconnect)),
    ):
        yield comfoconnect


class TestArguments:
    """Test the argument parsing."""

    def test_get_property_type_is_optional(self):
        """The property type defaults to a string."""
        args = parse("get-property", "1", "1", "8")
        assert (args.unit, args.subunit, args.property_id, args.property_type) == (1, 1, 8, 0x09)
        assert args.func is cli.run_get_property

    def test_get_property_type_can_be_given(self):
        """The property type can still be passed as the last positional argument."""
        args = parse("get-property", "--host", FAKE_HOST, "1", "1", "8", "3")
        assert args.property_type == 3
        assert args.host == FAKE_HOST

    def test_deregister_without_uuid_lists_apps(self):
        """Deregister without a UUID is allowed, it only lists the registered apps."""
        args = parse("deregister")
        assert args.uuid2 is None
        assert args.func is cli.run_deregister

    def test_deregister_still_accepts_pin(self):
        """The unused --pin of deregister is still accepted for existing scripts."""
        args = parse("deregister", OTHER_UUID, "--pin", "1234")
        assert args.uuid2 == OTHER_UUID

    def test_register_pin_is_an_int(self):
        """The PIN is parsed as an int."""
        assert parse("register", "--pin", "1234").pin == 1234

    def test_register_invalid_pin_fails_before_connecting(self):
        """A PIN that is not a number fails while parsing."""
        with pytest.raises(SystemExit):
            parse("register", "--pin", "12a4")

    @pytest.mark.parametrize(
        "argv",
        [
            ["register"],
            ["deregister"],
            ["set-speed", "low"],
            ["set-mode", "auto"],
            ["set-comfocool", "off"],
            ["set-boost", "on"],
            ["show-sensors"],
            ["show-sensor", "276"],
            ["get-property", "1", "1", "8"],
            ["set-property", "1", "1", "8", "3", "1"],
            ["list-nodes"],
        ],
    )
    def test_bridge_commands_accept_host_and_uuid(self, argv):
        """Every command that connects accepts --host and --uuid, with the default UUID."""
        args = parse(*argv)
        assert args.host is None
        assert args.uuid == DEFAULT_UUID
        assert callable(args.func)

        args = parse(*argv, "--host", FAKE_HOST, "--uuid", OTHER_UUID)
        assert args.host == FAKE_HOST
        assert args.uuid == OTHER_UUID

    def test_discover(self):
        """Discover accepts --host and repeated --broadcast."""
        args = parse("discover", "--broadcast", "192.0.2.255", "--broadcast", "198.51.100.255")
        assert args.broadcast == ["192.0.2.255", "198.51.100.255"]
        assert args.func is cli.run_discover

    def test_set_boost_timeout(self):
        """The boost timeout defaults to the library's default, and has a short option."""
        assert parse("set-boost", "on").timeout == 3600
        assert parse("set-boost", "on", "-t", "1200").timeout == 1200

    @pytest.mark.parametrize("debug", [False, True])
    def test_asyncio_debug_follows_debug_flag(self, debug):
        """asyncio debug mode is only enabled with --debug."""
        argv = ["--debug", "list-nodes"] if debug else ["list-nodes"]
        with patch.object(cli.asyncio, "run") as run, patch.object(cli, "run_list_nodes", MagicMock()):
            cli.main_cli(argv)
        assert run.call_args.kwargs["debug"] is debug


class TestConnected:
    """Test the connected() context manager."""

    async def test_disconnects_on_error(self, bridge):
        """The bridge is disconnected when the command fails."""
        with pytest.raises(RuntimeError):
            async with cli.connected(parse("list-nodes")):
                raise RuntimeError("boom")

        bridge.connect.assert_awaited_once_with(DEFAULT_UUID)
        bridge.disconnect.assert_awaited_once()

    async def test_disconnects_on_cancel(self, bridge):
        """The bridge is disconnected when the command is cancelled, like asyncio.run does on Ctrl-C."""
        started = asyncio.Event()

        async def command():
            async with cli.connected(parse("show-sensors")):
                started.set()
                await asyncio.sleep(3600)

        task = asyncio.create_task(command())
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        bridge.disconnect.assert_awaited_once()

    async def test_disconnects_when_not_allowed(self, bridge):
        """An unregistered UUID gives a clear error, and still cleans up."""
        bridge.connect.side_effect = ComfoConnectNotAllowed("not allowed")
        with pytest.raises(cli.CliError, match="register first"):
            async with cli.connected(parse("list-nodes")):
                pass

        bridge.disconnect.assert_awaited_once()

    async def test_uses_discovered_bridge(self, bridge):
        """The ComfoConnect is created for the discovered bridge."""
        async with cli.connected(parse("set-speed", "low", "--host", FAKE_HOST)):
            pass

        cli.discover_bridges.assert_awaited_once_with(FAKE_HOST)
        cli.ComfoConnect.assert_called_once_with(FAKE_HOST, FAKE_BRIDGE_UUID, bridge_type=0)


class TestCommands:
    """Test the commands themselves."""

    def test_bridge_not_found(self, bridge, capsys):
        """No bridge found is an error message, not a traceback."""
        cli.discover_bridges.return_value = []
        with pytest.raises(SystemExit) as exc:
            cli.main_cli(["set-speed", "low"])
        assert exc.value.code == 1
        assert "No bridge found" in capsys.readouterr().err

    def test_set_speed(self, bridge):
        """A command runs and disconnects."""
        cli.main_cli(["set-speed", "high"])
        bridge.set_speed.assert_awaited_once_with("high")
        bridge.disconnect.assert_awaited_once()

    def test_register_wrong_pin(self, bridge, capsys):
        """A wrong PIN is an error message, and the bridge is disconnected."""
        bridge.register.side_effect = ComfoConnectNotAllowed("not allowed")
        with pytest.raises(SystemExit) as exc:
            cli.main_cli(["register", "--pin", "1234"])
        assert exc.value.code == 1
        assert "check the PIN" in capsys.readouterr().err
        bridge.register.assert_awaited_once_with(DEFAULT_UUID, cli.DEFAULT_NAME, 1234)
        bridge.connect.assert_not_awaited()
        bridge.disconnect.assert_awaited_once()

    def test_deregister_lists_apps(self, bridge):
        """Deregister without a UUID only lists the registered apps."""
        cli.main_cli(["deregister"])
        bridge.cmd_deregister_app.assert_not_awaited()
        bridge.cmd_list_registered_apps.assert_awaited_once()

    def test_deregister_self(self, bridge, capsys):
        """Deregistering the UUID we connect with is refused before connecting."""
        with pytest.raises(SystemExit) as exc:
            cli.main_cli(["deregister", DEFAULT_UUID.upper()])
        assert exc.value.code == 1
        assert "can't deregister" in capsys.readouterr().err
        bridge.connect.assert_not_awaited()

    def test_show_unknown_sensor(self, bridge, capsys):
        """An unknown sensor is refused before connecting."""
        with pytest.raises(SystemExit) as exc:
            cli.main_cli(["show-sensor", "99999"])
        assert exc.value.code == 1
        assert "Unknown sensor" in capsys.readouterr().err
        bridge.connect.assert_not_awaited()

    def test_show_sensor_times_out(self, bridge, capsys, monkeypatch):
        """show-sensor gives up when the sensor never reports."""
        monkeypatch.setattr(cli, "SENSOR_VALUE_TIMEOUT", 0.01)
        with pytest.raises(SystemExit) as exc:
            cli.main_cli(["show-sensor", "276"])
        assert exc.value.code == 1
        assert "No value received" in capsys.readouterr().err
        bridge.disconnect.assert_awaited_once()

    def test_list_nodes(self, bridge, capsys, monkeypatch):
        """list-nodes prints every node with what it tells about itself, and goes on when a node can't tell."""
        monkeypatch.setattr(cli, "NODE_REQUEST_WAIT", 0)
        bridge.cmd_node_request = AsyncMock()
        bridge.nodes = {
            48: Node(node_id=48, product_id=ProductId.ZEHNDERGATEWAY, zone_id=0, mode=1),
            1: Node(node_id=1, product_id=ProductId.COMFOAIRQ, zone_id=1, mode=1),
            99: Node(node_id=99, product_id=200, zone_id=1, mode=1),
        }
        infos = {
            1: NodeInfo(name="My unit", model="ComfoAir Q450", article_number="000000000", serial_number="FAKE0000000000", firmware="R1.12.0", hardware_version=2, product_variant=2),
            48: NodeInfo(name="My bridge", model=None, article_number=None, serial_number="FAKE0000000001", firmware="R1.5.1", hardware_version=1, product_variant=0),
        }

        async def get_node_info(node_id):
            if node_id not in infos:
                raise ComfoConnectRmiError("RMI_ERROR (reference 9)")
            return infos[node_id]

        bridge.get_node_info = AsyncMock(side_effect=get_node_info)

        cli.main_cli(["list-nodes"])

        assert capsys.readouterr().out.splitlines() == [
            "Nodes on the ComfoNet bus:",
            "* node 1: product 1 (comfoairq), zone 1, mode 1",
            "  name: My unit, model: ComfoAir Q450, product variant: 2, firmware: R1.12.0, hardware version: 2, serial number: FAKE0000000000",
            "* node 48: product 5 (zehndergateway), zone 0, mode 1",
            "  name: My bridge, product variant: 0, firmware: R1.5.1, hardware version: 1, serial number: FAKE0000000001",
            "* node 99: product 200 (unknown), zone 1, mode 1",
            "  could not read the node info: RMI_ERROR (reference 9)",
        ]
        bridge.disconnect.assert_awaited_once()
