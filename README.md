# aiocomfoconnect

`aiocomfoconnect` is an asyncio Python 3 library for communicating with a Zehnder ComfoAir Q350/450/600 ventilation system. It's the successor of
[comfoconnect](https://github.com/michaelarnauts/comfoconnect).

The [home-assistant-comfoconnect](https://github.com/michaelarnauts/home-assistant-comfoconnect) is using this library.

It's compatible with Python 3.13 and higher.

## Installation

```shell
pip3 install aiocomfoconnect
```

## CLI Usage

```shell
$ python -m aiocomfoconnect --help

$ python -m aiocomfoconnect discover

$ python -m aiocomfoconnect register --host 192.168.1.213
$ python -m aiocomfoconnect deregister --host 192.168.1.213  # List the registered apps
$ python -m aiocomfoconnect deregister --host 192.168.1.213 <uuid>  # Deregister an app

$ python -m aiocomfoconnect set-speed away --host 192.168.1.213
$ python -m aiocomfoconnect set-speed low --host 192.168.1.213
$ python -m aiocomfoconnect set-mode auto --host 192.168.1.213
$ python -m aiocomfoconnect set-speed medium --host 192.168.1.213
$ python -m aiocomfoconnect set-speed high --host 192.168.1.213
$ python -m aiocomfoconnect set-boost on --host 192.168.1.213 --timeout 1200

$ python -m aiocomfoconnect set-comfocool auto --host 192.168.1.213
$ python -m aiocomfoconnect set-comfocool off --host 192.168.1.213

$ python -m aiocomfoconnect show-sensors --host 192.168.1.213
$ python -m aiocomfoconnect show-sensor 276 --host 192.168.1.213
$ python -m aiocomfoconnect show-sensor 276 --host 192.168.1.213 -f

$ python -m aiocomfoconnect get-property --host 192.168.1.213 1 1 8 9  # Unit 0x01, SubUnit 0x01, Property 0x08, Type STRING. See PROTOCOL-RMI.md
$ python -m aiocomfoconnect get-property --host 192.168.1.213 30 1 4 6  # The airflow of the low speed in m³/h (away=3, low=4, medium=5, high=6), Type INT16
$ python -m aiocomfoconnect set-property --host 192.168.1.213 30 1 4 6 120  # Set the airflow of the low speed to 120 m³/h
```

## Available methods

- `async connect()`: Connect to the bridge.
- `async disconnect()`: Disconnect from the bridge.
- `async register_sensor(sensor)`: Register a sensor.
- `async deregister_sensor(sensor)`: Deregister a sensor.
- `async get_mode()`: Get the ventilation mode.
- `async set_mode(mode)`: Set the ventilation mode. (auto / manual) Selecting `auto` also cancels the temporary fan-speed override and returns control to the unit's schedule.
- `async get_comfocool_mode()`: Get Comfocool mode
- `async set_comfocool_mode()`: Set Comfocool mode. (auto / off)
- `async get_speed()`: Get the ventilation speed, or `None` when no speed is set and the unit follows its schedule (auto mode).
- `async set_speed(speed)`: Set the ventilation speed. (away / low / medium / high)
- `async get_bypass()`: Get the bypass mode.
- `async set_bypass(mode, timeout=-1)`: Set the bypass mode. (auto / on / off)
- `async get_balance_mode()`: Get the balance mode.
- `async set_balance_mode(mode, timeout=-1)`: Set the balance mode. (balance / supply only / exhaust only)
- `async get_boost()`: Get the boost mode.
- `async set_boost(mode, timeout=3600)`: Set the boost mode. (boolean)
- `async get_away()`: Get the away mode.
- `async set_away(mode, timeout=3600)`: Set the away mode. (boolean)
- `async get_temperature_profile()`: Get the temperature profile, or `None` when no profile is set and the unit follows its schedule.
- `async set_temperature_profile(profile)`: Set the temperature profile. (warm / normal / cool)
- `async get_property(prop, node_id=None)`: Get the value of a property, e.g. `PROPERTY_RMOT_HEATING_THRESHOLD`. It is read from the node the property lives on: the ventilation unit, or the ComfoClime for the `PROPERTY_CLIME_*` properties. Pass `node_id` to read it from another node. A `NodeNotFoundException` is raised when the node isn't on the bus.
- `async set_property(prop, value, node_id=None)`: Set a property, on the same node as `get_property`.
- The airflow in m³/h of each fan speed is a property: `PROPERTY_FLOW_AWAY`, `PROPERTY_FLOW_LOW`, `PROPERTY_FLOW_MEDIUM` and `PROPERTY_FLOW_HIGH`, e.g. `await comfoconnect.set_property(PROPERTY_FLOW_LOW, 120)`.
- Properties that are an enum, like `PROPERTY_SENSOR_VENTILATION_TEMP_PASSIVE`, `PROPERTY_SENSOR_VENTILATION_HUMIDITY_COMFORT` and `PROPERTY_SENSOR_VENTILATION_HUMIDITY_PROTECTION` (off / auto / on), `PROPERTY_TEMPERATURE_PROFILE_MODE` (adaptive / fixed), `PROPERTY_CLIME_SEASON` and `PROPERTY_CLIME_TEMPERATURE_PROFILE`, have `options`: `get_property` returns the option and `set_property` takes it. `get_property_constraints` still uses the raw values.
- Temperatures in tenths of a degree, like `PROPERTY_RMOT_HEATING_THRESHOLD`, `PROPERTY_PROFILE_TEMPERATURE_NORMAL` and the ComfoClime temperatures, have `scale=0.1`: `get_property` and `get_property_constraints` return °C (215 becomes 21.5) and `set_property` takes °C.
- `async get_property_constraints(prop, node_id=None)`: Get the value of a numeric property, together with the range and step size the unit accepts.
- `bridge_type`: The type of the bridge (`GatewayType.LANC`, `SEASON` or `PRO`). Discovery reports it, and a ComfoConnect Pro is also recognised once a session has started.

### Low-level API

- `async cmd_start_session()`: Start a session.
- `async cmd_close_session()`: Close a session.
- `async cmd_list_registered_apps()`: List registered apps.
- `async cmd_register_app(uuid, device_name, pin)`: Register an app.
- `async cmd_deregister_app(uuid)`: Deregister an app.
- `async cmd_version_request()`: Request the bridge's version.
- `async cmd_time_request()`: Request the bridge's time.
- `async cmd_node_request()`: Retrigger the discovery of the nodes on the ComfoNet bus.
- `async cmd_rmi_request(message, node_id)`: Send a RMI request. When no `node_id` is given, the discovered ventilation unit is used, and a `VentilationUnitNotFoundException` is raised when the bridge hasn't announced one.
- `async cmd_rpdo_request(pdid, type, zone, timeout)`: Send a RPDO request.
- `async cmd_keepalive()`: Send a keepalive message.

## Examples

### Discovery of ComfoConnect LAN C Bridges

```python
import asyncio

from aiocomfoconnect import discover_bridges


async def main():
    """ ComfoConnect LAN C Bridge discovery example."""

    # Discover all ComfoConnect LAN C Bridges on the subnet.
    bridges = await discover_bridges()
    print(bridges)


if __name__ == "__main__":
    asyncio.run(main())
```

### Basic Example

```python
import asyncio

from aiocomfoconnect import ComfoConnect
from aiocomfoconnect.const import VentilationSpeed
from aiocomfoconnect.sensors import SENSORS


async def main(local_uuid, host, uuid):
    """ Basic example."""

    def sensor_callback(sensor, value):
        """ Print sensor updates. """
        print(f"{sensor.name} = {value}")

    # Connect to the Bridge
    comfoconnect = ComfoConnect(host, uuid, sensor_callback=sensor_callback)
    await comfoconnect.connect(local_uuid)

    # Register all sensors
    for key in SENSORS:
        await comfoconnect.register_sensor(SENSORS[key])

    # Set speed to LOW
    await comfoconnect.set_speed(VentilationSpeed.LOW)

    # Wait 2 minutes so we can see some sensor updates
    await asyncio.sleep(120)

    # Disconnect from the bridge
    await comfoconnect.disconnect()


if __name__ == "__main__":
    asyncio.run(main(local_uuid='00000000000000000000000000001337', host='192.168.1.20', uuid='00000000000000000000000000000055'))  # Replace with your bridge's IP and UUID
```

## Development Notes

### Protocol Documentation

- [ComfoConnect LAN C Protocol](docs/PROTOCOL.md)
- [PDO Sensors](docs/PROTOCOL-PDO.md)
- [RMI commands](docs/PROTOCOL-RMI.md)

### Decode network traffic

You can use the `scripts/decode_pcap.py` file to decode network traffic between the Mobile App and the ComfoConnect LAN C.
Make sure that the first TCP session in the capture is the connection between the bridge and the app. It's therefore recommended to start the capture before you open the app.

```shell
$ sudo tcpdump -i any -s 0 -w /tmp/capture.pcap tcp and port 56747
$ python3 script/decode_pcap.py /tmp/capture.pcap
```

### Generate zehnder_pb2.py file

```shell
python3 -m pip install grpcio-tools==1.73.0
python3 -m grpc_tools.protoc -Iprotobuf --python_out=aiocomfoconnect/protobuf protobuf/*.proto
```

### Docker

You can build a Docker image to make it easier to develop and experiment on your local machine. You can use the `docker build -t aiocomfoconnect .` or the shortcut `make build` command to create a docker image.

Next, you can run this image by running `docker run aiocomfoconnect`. Any args from `aiocomfoconnect` can be passed into this command, just like the `python3 -m aiocomfoconnect` command.

## Interesting 3th party repositories

* https://github.com/oysteing/comfoconnect-mqtt-bridge
