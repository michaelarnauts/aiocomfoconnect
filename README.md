# aiocomfoconnect

`aiocomfoconnect` is an asyncio Python 3 library for communicating with a Zehnder ComfoAir Q350/450/600 ventilation system. It's the successor of
[comfoconnect](https://github.com/michaelarnauts/comfoconnect).

It's compatible with Python 3.10 and higher.

## Installation

```shell
pip3 install aiocomfoconnect
```

## CLI Usage

```shell
$ python -m aiocomfoconnect --help

$ python -m aiocomfoconnect discover

$ python -m aiocomfoconnect register --host 192.168.1.213

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
```

## Available methods

- `async connect()`: Connect to the bridge.
- `async disconnect()`: Disconnect from the bridge.
- `async register_sensor(sensor)`: Register a sensor.
- `async deregister_sensor(sensor)`: Deregister a sensor.
- `async get_mode()`: Get the ventilation mode.
- `async set_mode(mode)`: Set the ventilation mode. (auto / manual)
- `async get_comfocool_mode()`: Get Comfocool mode
- `async set_comfocool_mode()`: Set Comfocool mode. (auto / off)
- `async get_speed()`: Get the ventilation speed.
- `async set_speed(speed)`: Set the ventilation speed. (away / low / medium / high)
- `async get_bypass()`: Get the bypass mode.
- `async set_bypass(mode, timeout=-1)`: Set the bypass mode. (auto / on / off)
- `async get_balance_mode()`: Get the balance mode.
- `async set_balance_mode(mode, timeout=-1)`: Set the balance mode. (balance / supply only / exhaust only)
- `async get_boost()`: Get the boost mode.
- `async set_boost(mode, timeout=-1)`: Set the boost mode. (boolean)
- `async get_away()`: Get the away mode.
- `async set_away(mode, timeout=-1)`: Set the away mode. (boolean)
- `async get_temperature_profile()`: Get the temperature profile.
- `async set_temperature_profile(profile)`: Set the temperature profile. (warm / normal / cool)
- `async get_sensor_ventmode_temperature_passive()`: Get the sensor based ventilation passive temperature control setting.
- `async set_sensor_ventmode_temperature_passive(mode)`: Set the sensor based ventilation passive temperature control setting. (auto / on / off)
- `async get_sensor_ventmode_humidity_comfort()`: Get the sensor based ventilation humidity comfort setting.
- `async set_sensor_ventmode_humidity_comfort(mode)`: Set the sensor based ventilation humidity comfort setting. (auto / on / off)
- `async get_sensor_ventmode_humidity_protection()`: Get the sensor based ventilation humidity protection setting.
- `async set_sensor_ventmode_humidity_protection(mode)`: Set the sensor based ventilation humidity protection setting. (auto / on / off)

### Low-level API

- `async cmd_start_session()`: Start a session.
- `async cmd_close_session()`: Close a session.
- `async cmd_list_registered_apps()`: List registered apps.
- `async cmd_register_app(uuid, device_name, pin)`: Register an app.
- `async cmd_deregister_app(uuid)`: Deregister an app.
- `async cmd_version_request()`: Request the bridge's version.
- `async cmd_time_request()`: Request the bridge's time.
- `async cmd_rmi_request(message, node_id)`: Send a RMI request.
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
