""" Provide an example CLI for Zehnder ComfoConnect LAN C. """
from __future__ import annotations

import argparse as argparse
import asyncio
import logging
from typing import Literal

from aiocomfoconnect import DEFAULT_NAME, DEFAULT_PIN, DEFAULT_UUID
from aiocomfoconnect.comfoconnect import ComfoConnect
from aiocomfoconnect.discovery import discover_bridges
from aiocomfoconnect.exceptions import ComfoConnectNotAllowed
from aiocomfoconnect.sensors import SENSORS

_LOGGER = logging.getLogger(__name__)


async def main(args):
    """Main function."""
    if args.action == "discover":
        await run_discover(args.host)

    elif args.action == "register":
        await run_register(args.host, args.uuid, args.name, args.pin)

    elif args.action == "set-speed":
        await run_set_speed(args.host, args.uuid, args.speed)

    elif args.action == "show-sensors":
        await run_show_sensors(args.host, args.uuid)

    else:
        raise Exception("Unknown action: " + args.action)


async def run_discover(host: str = None):
    """Discover all bridges on the network."""
    bridges = await discover_bridges(host)
    print("Discovered bridges:")
    for bridge in bridges:
        print(bridge)
        print()


async def run_register(host: str, uuid: str, name: str, pin: int):
    """Connect to a bridge."""
    # Discover bridge so we know the UUID
    bridges = await discover_bridges(host)
    if not bridges:
        raise Exception("No bridge found")

    # Connect to the bridge
    comfoconnect = ComfoConnect(bridges[0].host, bridges[0].uuid)
    await comfoconnect.connect(uuid)

    try:
        # Login with the bridge
        await comfoconnect.cmd_start_session()

        print(f"UUID {uuid} is already registered.")

    except ComfoConnectNotAllowed:
        # We probably are not registered yet...
        await comfoconnect.cmd_register_app(uuid, name, pin)

        # Connect to the bridge
        await comfoconnect.cmd_start_session()

    # ListRegisteredApps
    print("Registered applications:")
    reply = await comfoconnect.cmd_list_registered_apps()
    for app in reply.apps:
        print("* %s: %s" % (app.uuid.hex(), app.devicename))

    await comfoconnect.disconnect()


async def run_set_speed(host: str, uuid: str, speed: Literal["away", "low", "medium", "high"]):
    """Connect to a bridge."""
    # Discover bridge so we know the UUID
    bridges = await discover_bridges(host)
    if not bridges:
        raise Exception("No bridge found")

    # Connect to the bridge
    comfoconnect = ComfoConnect(bridges[0].host, bridges[0].uuid)
    await comfoconnect.connect(uuid)
    await comfoconnect.cmd_start_session()

    await comfoconnect.set_speed(speed)

    await comfoconnect.disconnect()


async def run_show_sensors(host: str, uuid: str):
    """Connect to a bridge."""
    loop = asyncio.get_running_loop()

    # Discover bridge so we know the UUID
    bridges = await discover_bridges(host, loop=loop)
    if not bridges:
        raise Exception("No bridge found")

    def sensor_callback(sensor, value):
        """Print sensor updates."""
        print("{sensor:>40}: {value} {unit}".format(sensor=sensor.name, value=value, unit=sensor.unit or ""))

    # Connect to the bridge
    comfoconnect = ComfoConnect(bridges[0].host, bridges[0].uuid, callback=sensor_callback)
    await comfoconnect.connect(uuid)
    await comfoconnect.cmd_start_session()

    # Register all sensors
    for key in SENSORS:
        await comfoconnect.register_sensor(SENSORS[key])

    # Wait for updates
    await asyncio.sleep(60)
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

    p_set_speed = subparsers.add_parser("set-speed", help="set the fan speed")
    p_set_speed.add_argument("speed", help="Fan speed", choices=["low", "medium", "high", "away"])
    p_set_speed.add_argument("--host", help="Host address of the bridge")
    p_set_speed.add_argument("--uuid", help="UUID of this app", default=DEFAULT_UUID)

    p_sensors = subparsers.add_parser("show-sensors", help="show the sensor values")
    p_sensors.add_argument("--host", help="Host address of the bridge")
    p_sensors.add_argument("--uuid", help="UUID of this app", default=DEFAULT_UUID)

    args = parser.parse_args()

    if args.debug:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.WARNING)

    try:
        asyncio.run(main(args), debug=True)
    except KeyboardInterrupt:
        pass
