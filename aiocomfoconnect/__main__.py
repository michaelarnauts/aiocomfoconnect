""" aiocomfoconnect CLI application """

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from asyncio import Future
from typing import Literal

from aiocomfoconnect import DEFAULT_NAME, DEFAULT_PIN, DEFAULT_UUID
from aiocomfoconnect.comfoconnect import ComfoConnect
from aiocomfoconnect.discovery import discover_bridges
from aiocomfoconnect.exceptions import (
    AioComfoConnectNotConnected,
    AioComfoConnectTimeout,
    BridgeNotFoundException,
    ComfoConnectNotAllowed,
    UnknownActionException,
)
from aiocomfoconnect.properties import Property
from aiocomfoconnect.sensors import SENSORS

_LOGGER = logging.getLogger(__name__)


async def main(args):
    """Main function."""
    if args.action == "discover":
        await run_discover(args.host)

    elif args.action == "register":
        await run_register(args.host, args.uuid, args.name, args.pin)

    elif args.action == "deregister":
        await run_deregister(args.host, args.uuid, args.uuid2)

    elif args.action == "set-speed":
        await run_set_speed(args.host, args.uuid, args.speed)

    elif args.action == "set-mode":
        await run_set_mode(args.host, args.uuid, args.mode)

    elif args.action == "set-comfocool":
        await run_set_comfocool(args.host, args.uuid, args.mode)

    elif args.action == "set-boost":
        await run_set_boost(args.host, args.uuid, args.mode, args.timeout)

    elif args.action == "show-sensors":
        await run_show_sensors(args.host, args.uuid)

    elif args.action == "show-sensor":
        await run_show_sensor(args.host, args.uuid, args.sensor, args.follow)

    elif args.action == "get-property":
        await run_get_property(args.host, args.uuid, args.node_id, args.unit, args.subunit, args.property_id, args.property_type)

    elif args.action == "get-flow-for-speed":
        await run_get_flow_for_speed(args.host, args.uuid, args.speed)

    elif args.action == "set-flow-for-speed":
        await run_set_flow_for_speed(args.host, args.uuid, args.speed, args.flow)

    else:
        raise UnknownActionException("Unknown action: " + args.action)


async def run_discover(host: str = None):
    """Discover all bridges on the network."""
    bridges = await discover_bridges(host)
    print("Discovered bridges:")
    for bridge in bridges:
        print(bridge)
        print()


async def run_register(host: str, uuid: str, name: str, pin: int):
    """Register an app on the bridge."""
    # Discover bridge so we know the UUID
    bridges = await discover_bridges(host)
    if not bridges:
        raise BridgeNotFoundException("No bridge found")

    # Connect to the bridge
    comfoconnect = ComfoConnect(bridges[0].host, bridges[0].uuid)

    try:
        # Login with the bridge
        await comfoconnect.connect(uuid)
        print(f"UUID {uuid} is already registered.")

    except ComfoConnectNotAllowed:
        # We probably are not registered yet...
        try:
            await comfoconnect.cmd_register_app(uuid, name, pin)
        except ComfoConnectNotAllowed:
            await comfoconnect.disconnect()
            print("Registration failed. Please check the PIN.")
            sys.exit(1)

        print(f"UUID {uuid} is now registered.")

        # Connect to the bridge
        await comfoconnect.cmd_start_session(True)

    # ListRegisteredApps
    print()
    print("Registered applications:")
    reply = await comfoconnect.cmd_list_registered_apps()
    for app in reply.apps:
        print(f"* {app.uuid.hex()}: {app.devicename}")

    await comfoconnect.disconnect()


async def run_deregister(host: str, uuid: str, uuid2: str):
    """Deregister an app on the bridge."""
    # Discover bridge so we know the UUID
    bridges = await discover_bridges(host)
    if not bridges:
        raise BridgeNotFoundException("No bridge found")

    # Connect to the bridge
    comfoconnect = ComfoConnect(bridges[0].host, bridges[0].uuid)
    try:
        await comfoconnect.connect(uuid)
    except ComfoConnectNotAllowed:
        print("Could not connect to bridge. Please register first.")
        sys.exit(1)

    if uuid2:
        await comfoconnect.cmd_deregister_app(uuid2)

    # ListRegisteredApps
    print()
    print("Registered applications:")
    reply = await comfoconnect.cmd_list_registered_apps()
    for app in reply.apps:
        print(f"* {app.uuid.hex()}: {app.devicename}")

    await comfoconnect.disconnect()


async def run_set_speed(host: str, uuid: str, speed: Literal["away", "low", "medium", "high"]):
    """Set ventilation speed."""
    # Discover bridge so we know the UUID
    bridges = await discover_bridges(host)
    if not bridges:
        raise BridgeNotFoundException("No bridge found")

    # Connect to the bridge
    comfoconnect = ComfoConnect(bridges[0].host, bridges[0].uuid)
    try:
        await comfoconnect.connect(uuid)
    except ComfoConnectNotAllowed:
        print("Could not connect to bridge. Please register first.")
        sys.exit(1)

    await comfoconnect.set_speed(speed)

    await comfoconnect.disconnect()


async def run_set_mode(host: str, uuid: str, mode: Literal["auto", "manual"]):
    """Set ventilation mode."""
    # Discover bridge so we know the UUID
    bridges = await discover_bridges(host)
    if not bridges:
        raise BridgeNotFoundException("No bridge found")

    # Connect to the bridge
    comfoconnect = ComfoConnect(bridges[0].host, bridges[0].uuid)
    try:
        await comfoconnect.connect(uuid)
    except ComfoConnectNotAllowed:
        print("Could not connect to bridge. Please register first.")
        sys.exit(1)

    await comfoconnect.set_mode(mode)

    await comfoconnect.disconnect()


async def run_set_comfocool(host: str, uuid: str, mode: Literal["auto", "off"]):
    """Set comfocool mode."""
    # Discover bridge so we know the UUID
    bridges = await discover_bridges(host)
    if not bridges:
        raise BridgeNotFoundException("No bridge found")

    # Connect to the bridge
    comfoconnect = ComfoConnect(bridges[0].host, bridges[0].uuid)
    try:
        await comfoconnect.connect(uuid)
    except ComfoConnectNotAllowed:
        print("Could not connect to bridge. Please register first.")
        sys.exit(1)

    await comfoconnect.set_comfocool_mode(mode)

    await comfoconnect.disconnect()


async def run_set_boost(host: str, uuid: str, mode: Literal["on", "off"], timeout: int):
    """Set boost."""
    # Discover bridge so we know the UUID
    bridges = await discover_bridges(host)
    if not bridges:
        raise BridgeNotFoundException("No bridge found")

    # Connect to the bridge
    comfoconnect = ComfoConnect(bridges[0].host, bridges[0].uuid)
    try:
        await comfoconnect.connect(uuid)
    except ComfoConnectNotAllowed:
        print("Could not connect to bridge. Please register first.")
        sys.exit(1)

    await comfoconnect.set_boost(mode == "on", timeout)

    await comfoconnect.disconnect()


async def run_show_sensors(host: str, uuid: str):
    """Show all sensors."""
    # Discover bridge so we know the UUID
    bridges = await discover_bridges(host)
    if not bridges:
        raise BridgeNotFoundException("No bridge found")

    def alarm_callback(node_id, errors):
        """Print alarm updates."""
        print(f"Alarm received for Node {node_id}:")
        for error_id, error in errors.items():
            print(f"* {error_id}: {error}")

    def sensor_callback(sensor, value):
        """Print sensor updates."""
        print(f"{sensor.name:>40}: {value} {sensor.unit or ''}")

    # Connect to the bridge
    comfoconnect = ComfoConnect(bridges[0].host, bridges[0].uuid, sensor_callback=sensor_callback, alarm_callback=alarm_callback)
    try:
        await comfoconnect.connect(uuid)
    except ComfoConnectNotAllowed:
        print("Could not connect to bridge. Please register first.")
        sys.exit(1)

    # Register all sensors
    for sensor in SENSORS.values():
        await comfoconnect.register_sensor(sensor)

    try:
        while True:
            # Wait for updates and send a keepalive every 30 seconds
            await asyncio.sleep(30)

            try:
                print("Sending keepalive...")
                # Use cmd_time_request as a keepalive since cmd_keepalive doesn't send back a reply we can wait for
                await comfoconnect.cmd_time_request()
            except AioComfoConnectNotConnected:
                print("Got AioComfoConnectNotConnected")
            except AioComfoConnectTimeout:
                print("Got AioComfoConnectTimeout")

    except KeyboardInterrupt:
        pass

    print("Disconnecting...")
    await comfoconnect.disconnect()


async def run_show_sensor(host: str, uuid: str, sensor: int, follow=False):
    """Show a sensor."""
    result = Future()

    # Discover bridge so we know the UUID
    bridges = await discover_bridges(host)
    if not bridges:
        raise BridgeNotFoundException("No bridge found")

    def sensor_callback(sensor_, value):
        """Print sensor update."""
        print(value)
        if not result.done():
            result.set_result(value)

    # Connect to the bridge
    comfoconnect = ComfoConnect(bridges[0].host, bridges[0].uuid, sensor_callback=sensor_callback)
    try:
        await comfoconnect.connect(uuid)
    except ComfoConnectNotAllowed:
        print("Could not connect to bridge. Please register first.")
        sys.exit(1)

    if not sensor in SENSORS:
        print(f"Unknown sensor with ID {sensor}")
        sys.exit(1)

    # Register sensors
    await comfoconnect.register_sensor(SENSORS[sensor])

    # Wait for value
    await result

    # Follow for updates if requested
    if follow:
        try:
            while True:
                # Wait for updates and send a keepalive every 30 seconds
                await asyncio.sleep(30)

                try:
                    print("Sending keepalive...")
                    # Use cmd_time_request as a keepalive since cmd_keepalive doesn't send back a reply we can wait for
                    await comfoconnect.cmd_time_request()
                except AioComfoConnectNotConnected:
                    print("Got AioComfoConnectNotConnected")
                except AioComfoConnectTimeout:
                    print("Got AioComfoConnectTimeout")

        except KeyboardInterrupt:
            pass

    # Disconnect
    await comfoconnect.disconnect()


async def run_get_property(host: str, uuid: str, node_id: int, unit: int, subunit: int, property_id: int, property_type: int):
    """Get a property."""
    # Discover bridge so we know the UUID
    bridges = await discover_bridges(host)
    if not bridges:
        raise BridgeNotFoundException("No bridge found")

    # Connect to the bridge
    comfoconnect = ComfoConnect(bridges[0].host, bridges[0].uuid)
    try:
        await comfoconnect.connect(uuid)
    except ComfoConnectNotAllowed:
        print("Could not connect to bridge. Please register first.")
        sys.exit(1)

    print(await comfoconnect.get_property(Property(unit, subunit, property_id, property_type), node_id))

    await comfoconnect.disconnect()


async def run_get_flow_for_speed(host: str, uuid: str, speed: Literal["away", "low", "medium", "high"]):
    """Get the configured airflow for the specified speed."""
    # Discover bridge so we know the UUID
    bridges = await discover_bridges(host)
    if not bridges:
        raise BridgeNotFoundException("No bridge found")

    # Connect to the bridge
    comfoconnect = ComfoConnect(bridges[0].host, bridges[0].uuid)
    try:
        await comfoconnect.connect(uuid)
    except ComfoConnectNotAllowed:
        print("Could not connect to bridge. Please register first.")
        sys.exit(1)

    print(await comfoconnect.get_flow_for_speed(speed))

    await comfoconnect.disconnect()


async def run_set_flow_for_speed(host: str, uuid: str, speed: Literal["away", "low", "medium", "high"], desired_flow: int):
    """Set the configured airflow for the specified speed."""
    # Discover bridge so we know the UUID
    bridges = await discover_bridges(host)
    if not bridges:
        raise BridgeNotFoundException("No bridge found")

    # Connect to the bridge
    comfoconnect = ComfoConnect(bridges[0].host, bridges[0].uuid)
    try:
        await comfoconnect.connect(uuid)
    except ComfoConnectNotAllowed:
        print("Could not connect to bridge. Please register first.")
        sys.exit(1)

    await comfoconnect.set_flow_for_speed(speed, desired_flow)

    await comfoconnect.disconnect()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--debug", "-d", help="Enable debug logging", default=False, action="store_true")
    subparsers = parser.add_subparsers(required=True, dest="action")

    p_discover = subparsers.add_parser("discover", help="discover ComfoConnect LAN C devices on your network")
    p_discover.add_argument("--host", help="Host address of the bridge")

    p_register = subparsers.add_parser("register", help="register on a ComfoConnect LAN C device")
    p_register.add_argument("--pin", help="PIN code to register on the bridge", default=DEFAULT_PIN)
    p_register.add_argument("--host", help="Host address of the bridge")
    p_register.add_argument("--uuid", help="UUID of this app", default=DEFAULT_UUID)
    p_register.add_argument("--name", help="Name of this app", default=DEFAULT_NAME)

    p_register = subparsers.add_parser("deregister", help="deregister on a ComfoConnect LAN C device")
    p_register.add_argument("uuid2", help="UUID of the app to deregister", default=None)
    p_register.add_argument("--pin", help="PIN code to register on the bridge", default=DEFAULT_PIN)
    p_register.add_argument("--host", help="Host address of the bridge")
    p_register.add_argument("--uuid", help="UUID of this app", default=DEFAULT_UUID)

    p_set_speed = subparsers.add_parser("set-speed", help="set the fan speed")
    p_set_speed.add_argument("speed", help="Fan speed", choices=["low", "medium", "high", "away"])
    p_set_speed.add_argument("--host", help="Host address of the bridge")
    p_set_speed.add_argument("--uuid", help="UUID of this app", default=DEFAULT_UUID)

    p_set_mode = subparsers.add_parser("set-mode", help="set operation mode")
    p_set_mode.add_argument("mode", help="Operation mode", choices=["auto", "manual"])
    p_set_mode.add_argument("--host", help="Host address of the bridge")
    p_set_mode.add_argument("--uuid", help="UUID of this app", default=DEFAULT_UUID)

    p_set_mode = subparsers.add_parser("set-comfocool", help="set comfocool mode")
    p_set_mode.add_argument("mode", help="Comfocool mode", choices=["auto", "off"])
    p_set_mode.add_argument("--host", help="Host address of the bridge")
    p_set_mode.add_argument("--uuid", help="UUID of this app", default=DEFAULT_UUID)

    p_set_boost = subparsers.add_parser("set-boost", help="trigger or cancel a boost")
    p_set_boost.add_argument("mode", help="Boost mode", choices=["on", "off"])
    p_set_boost.add_argument("--host", help="Host address of the bridge")
    p_set_boost.add_argument("--uuid", help="UUID of this app", default=DEFAULT_UUID)
    p_set_boost.add_argument("--timeout", "-t", help="Timeout in seconds", type=int, default=600)

    p_sensors = subparsers.add_parser("show-sensors", help="show the sensor values")
    p_sensors.add_argument("--host", help="Host address of the bridge")
    p_sensors.add_argument("--uuid", help="UUID of this app", default=DEFAULT_UUID)

    p_sensor = subparsers.add_parser("show-sensor", help="show a single sensor value")
    p_sensor.add_argument("sensor", help="The ID of the sensor", type=int)
    p_sensor.add_argument("--host", help="Host address of the bridge")
    p_sensor.add_argument("--uuid", help="UUID of this app", default=DEFAULT_UUID)
    p_sensor.add_argument("--follow", "-f", help="Follow", default=False, action="store_true")

    p_sensor = subparsers.add_parser("get-property", help="show a property value")
    p_sensor.add_argument("unit", help="The Unit of the property", type=int)
    p_sensor.add_argument("subunit", help="The Subunit of the property", type=int)
    p_sensor.add_argument("property_id", help="The id of the property", type=int)
    p_sensor.add_argument("property_type", help="The type of the property", type=int, default=0x09)

    p_sensor.add_argument("--node_id", help="The Node ID of the query", type=int, default=0x01)
    p_sensor.add_argument("--host", help="Host address of the bridge")
    p_sensor.add_argument("--uuid", help="UUID of this app", default=DEFAULT_UUID)

    p_get_flow_speed = subparsers.add_parser("get-flow-for-speed", help="Get m³/h for given speed")
    p_get_flow_speed.add_argument("speed", help="Fan speed", choices=["low", "medium", "high", "away"])
    p_get_flow_speed.add_argument("--host", help="Host address of the bridge")
    p_get_flow_speed.add_argument("--uuid", help="UUID of this app", default=DEFAULT_UUID)

    p_set_flow_speed = subparsers.add_parser("set-flow-for-speed", help="Set m³/h for given speed")
    p_set_flow_speed.add_argument("speed", help="Fan speed", choices=["low", "medium", "high", "away"])
    p_set_flow_speed.add_argument("flow", help="Desired airflow in m³/h", type=int)
    p_set_flow_speed.add_argument("--host", help="Host address of the bridge")
    p_set_flow_speed.add_argument("--uuid", help="UUID of this app", default=DEFAULT_UUID)

    arguments = parser.parse_args()

    if arguments.debug:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.WARNING)

    try:
        asyncio.run(main(arguments), debug=True)
    except KeyboardInterrupt:
        pass
