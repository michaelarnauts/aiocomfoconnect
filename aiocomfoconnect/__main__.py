"""aiocomfoconnect CLI application"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from contextlib import asynccontextmanager
from typing import AsyncIterator

from aiocomfoconnect import DEFAULT_NAME, DEFAULT_PIN, DEFAULT_UUID
from aiocomfoconnect.comfoconnect import ComfoConnect
from aiocomfoconnect.const import ProductId
from aiocomfoconnect.discovery import discover_bridges
from aiocomfoconnect.exceptions import (
    AioComfoConnectNotConnected,
    AioComfoConnectTimeout,
    BridgeNotFoundException,
    ComfoConnectNotAllowed,
)
from aiocomfoconnect.properties import Property
from aiocomfoconnect.sensors import SENSORS

_LOGGER = logging.getLogger(__name__)

PRODUCT_NAMES = {value: name.lower() for name, value in vars(ProductId).items() if not name.startswith("_")}

# How long show-sensor waits for the first value. The bridge only reports a sensor after the sensor hold (5 seconds by default).
SENSOR_VALUE_TIMEOUT = 30

# How often we send a keepalive while following sensor updates.
KEEPALIVE_INTERVAL = 30


class CliError(Exception):
    """An error that is shown to the user without a traceback."""


@asynccontextmanager
async def connected(args, *, connect: bool = True, **kwargs) -> AsyncIterator[ComfoConnect]:
    """Discover the bridge, connect to it and always disconnect afterwards.

    The disconnect also happens when the command fails or is cancelled (Ctrl-C).
    With connect=False, the caller opens the session itself (eg. by registering).
    """
    bridges = await discover_bridges(args.host)
    if not bridges:
        raise BridgeNotFoundException("No bridge found")

    comfoconnect = ComfoConnect(bridges[0].host, bridges[0].uuid, bridge_type=bridges[0].bridge_type, **kwargs)
    try:
        if connect:
            try:
                await comfoconnect.connect(args.uuid)
            except ComfoConnectNotAllowed as exc:
                raise CliError("Could not connect to bridge. Please register first.") from exc
        yield comfoconnect
    finally:
        await comfoconnect.disconnect()


async def follow(comfoconnect: ComfoConnect):
    """Keep the session open to receive updates, until cancelled (Ctrl-C)."""
    while True:
        await asyncio.sleep(KEEPALIVE_INTERVAL)

        try:
            print("Sending keepalive...")
            # Use cmd_time_request as a keepalive since cmd_keepalive doesn't send back a reply we can wait for
            await comfoconnect.cmd_time_request()
        except AioComfoConnectNotConnected:
            print("Got AioComfoConnectNotConnected")
        except AioComfoConnectTimeout:
            print("Got AioComfoConnectTimeout")


async def print_registered_apps(comfoconnect: ComfoConnect):
    """Print the apps that are registered on the bridge."""
    print()
    print("Registered applications:")
    reply = await comfoconnect.cmd_list_registered_apps()
    for app in reply.apps:
        print(f"* {app.uuid.hex()}: {app.devicename}")


async def run_discover(args):
    """Discover all bridges on the network."""
    bridges = await discover_bridges(args.host, broadcast_addresses=args.broadcast)
    print("Discovered bridges:")
    for bridge in bridges:
        print(bridge)
        print()


async def run_register(args):
    """Register an app on the bridge."""
    async with connected(args, connect=False) as comfoconnect:
        try:
            registered = await comfoconnect.register(args.uuid, args.name, args.pin)
        except ComfoConnectNotAllowed as exc:
            raise CliError("Registration failed. Please check the PIN.") from exc

        if registered:
            print(f"UUID {args.uuid} is now registered.")
        else:
            print(f"UUID {args.uuid} is already registered.")

        await print_registered_apps(comfoconnect)


async def run_deregister(args):
    """Deregister an app on the bridge, or list the registered apps when no UUID is given."""
    if args.uuid2 and args.uuid2.lower() == args.uuid.lower():
        raise CliError("You can't deregister the UUID you are connecting with. Use --uuid to connect with another registered UUID.")

    async with connected(args) as comfoconnect:
        if args.uuid2:
            await comfoconnect.cmd_deregister_app(args.uuid2)

        await print_registered_apps(comfoconnect)


async def run_set_speed(args):
    """Set ventilation speed."""
    async with connected(args) as comfoconnect:
        await comfoconnect.set_speed(args.speed)


async def run_set_mode(args):
    """Set ventilation mode."""
    async with connected(args) as comfoconnect:
        await comfoconnect.set_mode(args.mode)


async def run_set_comfocool(args):
    """Set comfocool mode."""
    async with connected(args) as comfoconnect:
        await comfoconnect.set_comfocool_mode(args.mode)


async def run_set_boost(args):
    """Set boost."""
    async with connected(args) as comfoconnect:
        await comfoconnect.set_boost(args.mode == "on", args.timeout)


async def run_show_sensors(args):
    """Show all sensors."""

    def alarm_callback(node_id, errors):
        """Print alarm updates."""
        print(f"Alarm received for Node {node_id}:")
        for error_id, error in errors.items():
            print(f"* {error_id}: {error}")

    def sensor_callback(sensor, value):
        """Print sensor updates."""
        print(f"{sensor.name:>40}: {value} {sensor.unit or ''}")

    async with connected(args, sensor_callback=sensor_callback, alarm_callback=alarm_callback) as comfoconnect:
        for sensor in SENSORS.values():
            await comfoconnect.register_sensor(sensor)

        await follow(comfoconnect)


async def run_show_sensor(args):
    """Show a sensor."""
    if args.sensor not in SENSORS:
        raise CliError(f"Unknown sensor with ID {args.sensor}")

    result = asyncio.get_running_loop().create_future()

    def sensor_callback(sensor_, value):
        """Print sensor update."""
        print(value)
        if not result.done():
            result.set_result(value)

    async with connected(args, sensor_callback=sensor_callback) as comfoconnect:
        await comfoconnect.register_sensor(SENSORS[args.sensor])

        try:
            await asyncio.wait_for(result, SENSOR_VALUE_TIMEOUT)
        except asyncio.TimeoutError as exc:
            raise CliError(f"No value received for sensor {args.sensor} within {SENSOR_VALUE_TIMEOUT} seconds") from exc

        if args.follow:
            await follow(comfoconnect)


async def run_get_property(args):
    """Get a property."""
    async with connected(args) as comfoconnect:
        print(await comfoconnect.get_property(Property(args.unit, args.subunit, args.property_id, args.property_type), args.node_id))


async def run_set_property(args):
    """Set a property and print the value that is read back."""
    async with connected(args) as comfoconnect:
        await comfoconnect.set_property_typed(args.unit, args.subunit, args.property_id, args.value, args.property_type, node_id=args.node_id)
        print(await comfoconnect.get_property(Property(args.unit, args.subunit, args.property_id, args.property_type), args.node_id))


async def run_list_nodes(args):
    """List the nodes that the bridge sees on the ComfoNet bus."""
    async with connected(args) as comfoconnect:
        await comfoconnect.cmd_node_request()
        # Nodes arrive as unsolicited notifications, so give the bridge a moment to report them all.
        await asyncio.sleep(2)

        print("Nodes on the ComfoNet bus:")
        for node in sorted(comfoconnect.nodes.values(), key=lambda n: n.node_id):
            product = PRODUCT_NAMES.get(node.product_id, "unknown")
            print(f"* node {node.node_id}: product {node.product_id} ({product}), zone {node.zone_id}, mode {node.mode}")


async def run_get_flow_for_speed(args):
    """Get the configured airflow for the specified speed."""
    async with connected(args) as comfoconnect:
        print(await comfoconnect.get_flow_for_speed(args.speed))


async def run_set_flow_for_speed(args):
    """Set the configured airflow for the specified speed."""
    async with connected(args) as comfoconnect:
        await comfoconnect.set_flow_for_speed(args.speed, args.flow)


async def main(args):
    """Run the selected command."""
    await args.func(args)


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--debug", "-d", help="Enable debug logging", default=False, action="store_true")
    subparsers = parser.add_subparsers(required=True, dest="action")

    # Arguments that every command that connects to the bridge accepts.
    bridge = argparse.ArgumentParser(add_help=False)
    bridge.add_argument("--host", help="Host address of the bridge")
    bridge.add_argument("--uuid", help="UUID of this app", default=DEFAULT_UUID)

    p_discover = subparsers.add_parser("discover", help="discover ComfoConnect LAN C devices on your network")
    p_discover.add_argument("--host", help="Host address of the bridge")
    p_discover.add_argument("--broadcast", help="Broadcast address to search (eg. 192.168.1.255), can be repeated", action="append")
    p_discover.set_defaults(func=run_discover)

    p_register = subparsers.add_parser("register", parents=[bridge], help="register on a ComfoConnect LAN C device")
    p_register.add_argument("--pin", help="PIN code to register on the bridge", type=int, default=DEFAULT_PIN)
    p_register.add_argument("--name", help="Name of this app", default=DEFAULT_NAME)
    p_register.set_defaults(func=run_register)

    p_deregister = subparsers.add_parser("deregister", parents=[bridge], help="deregister an app on a ComfoConnect LAN C device, or list the registered apps")
    p_deregister.add_argument("uuid2", help="UUID of the app to deregister (omit to only list the registered apps)", nargs="?", default=None)
    # Deregistering doesn't need a PIN. Still accepted so existing scripts keep working.
    p_deregister.add_argument("--pin", help=argparse.SUPPRESS, type=int, default=DEFAULT_PIN)
    p_deregister.set_defaults(func=run_deregister)

    p_set_speed = subparsers.add_parser("set-speed", parents=[bridge], help="set the fan speed")
    p_set_speed.add_argument("speed", help="Fan speed", choices=["low", "medium", "high", "away"])
    p_set_speed.set_defaults(func=run_set_speed)

    p_set_mode = subparsers.add_parser("set-mode", parents=[bridge], help="set operation mode")
    p_set_mode.add_argument("mode", help="Operation mode", choices=["auto", "manual"])
    p_set_mode.set_defaults(func=run_set_mode)

    p_set_comfocool = subparsers.add_parser("set-comfocool", parents=[bridge], help="set comfocool mode")
    p_set_comfocool.add_argument("mode", help="Comfocool mode", choices=["auto", "off"])
    p_set_comfocool.set_defaults(func=run_set_comfocool)

    p_set_boost = subparsers.add_parser("set-boost", parents=[bridge], help="trigger or cancel a boost")
    p_set_boost.add_argument("mode", help="Boost mode", choices=["on", "off"])
    p_set_boost.add_argument("--timeout", "-t", help="Timeout in seconds (default: %(default)s)", type=int, default=600)
    p_set_boost.set_defaults(func=run_set_boost)

    p_sensors = subparsers.add_parser("show-sensors", parents=[bridge], help="show the sensor values")
    p_sensors.set_defaults(func=run_show_sensors)

    p_sensor = subparsers.add_parser("show-sensor", parents=[bridge], help="show a single sensor value")
    p_sensor.add_argument("sensor", help="The ID of the sensor", type=int)
    p_sensor.add_argument("--follow", "-f", help="Follow", default=False, action="store_true")
    p_sensor.set_defaults(func=run_show_sensor)

    p_get_property = subparsers.add_parser("get-property", parents=[bridge], help="show a property value")
    p_get_property.add_argument("unit", help="The Unit of the property", type=int)
    p_get_property.add_argument("subunit", help="The Subunit of the property", type=int)
    p_get_property.add_argument("property_id", help="The id of the property", type=int)
    p_get_property.add_argument("property_type", help="The type of the property (default: %(default)s, a string)", type=int, nargs="?", default=0x09)
    p_get_property.add_argument("--node_id", help="The Node ID of the query (defaults to the discovered ventilation unit)", type=int, default=None)
    p_get_property.set_defaults(func=run_get_property)

    p_set_property = subparsers.add_parser("set-property", parents=[bridge], help="set a property value")
    p_set_property.add_argument("unit", help="The Unit of the property", type=int)
    p_set_property.add_argument("subunit", help="The Subunit of the property", type=int)
    p_set_property.add_argument("property_id", help="The id of the property", type=int)
    p_set_property.add_argument("property_type", help="The type of the property", type=int)
    p_set_property.add_argument("value", help="The raw value to write", type=int)
    p_set_property.add_argument("--node_id", help="The Node ID to write to (defaults to the discovered ventilation unit)", type=int, default=None)
    p_set_property.set_defaults(func=run_set_property)

    p_list_nodes = subparsers.add_parser("list-nodes", parents=[bridge], help="list the nodes on the ComfoNet bus")
    p_list_nodes.set_defaults(func=run_list_nodes)

    p_get_flow_speed = subparsers.add_parser("get-flow-for-speed", parents=[bridge], help="Get m³/h for given speed")
    p_get_flow_speed.add_argument("speed", help="Fan speed", choices=["low", "medium", "high", "away"])
    p_get_flow_speed.set_defaults(func=run_get_flow_for_speed)

    p_set_flow_speed = subparsers.add_parser("set-flow-for-speed", parents=[bridge], help="Set m³/h for given speed")
    p_set_flow_speed.add_argument("speed", help="Fan speed", choices=["low", "medium", "high", "away"])
    p_set_flow_speed.add_argument("flow", help="Desired airflow in m³/h", type=int)
    p_set_flow_speed.set_defaults(func=run_set_flow_for_speed)

    return parser


def main_cli(argv=None):
    """Parse arguments and start async event loop."""
    arguments = build_parser().parse_args(argv)

    if arguments.debug:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.WARNING)

    try:
        asyncio.run(main(arguments), debug=arguments.debug)
    except KeyboardInterrupt:
        pass
    except (BridgeNotFoundException, CliError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main_cli()
