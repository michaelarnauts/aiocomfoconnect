# RMI Protocol

A † marks information that comes from the official ComfoControl app (what it reads, writes or names), but that has
not been checked on a unit.

## Nodes

A RMI message is send towards a Node. The node ids are not fixed: the bridge announces the nodes that are available
with `CnNodeNotification` messages when a session starts, and the ventilation unit is the node whose `productId` is
`1` (ComfoAirQ) or `8` (ComfoAir Flex). On a ComfoAirQ with a ComfoConnect LAN C, this typically results in:

| Node | Description                   |
|------|-------------------------------|
| 0x01 | The Ventilation Unit itself   |
| 0x30 | The ComfoConnect LAN C device |

On other setups the ids differ. A ComfoAir Flex has for example been seen at node `0x2D` (45), with its connection
board at node `0x29` (41).

## Units

The Ventilation Unit is seperated into multiple Units, and sometimes even SubUnits. Here is a list of some existing units:

| ID   | # of SubUnits | Name              | Responsible for                                                                             |
|------|---------------|-------------------|---------------------------------------------------------------------------------------------|
| 0x01 | 1             | NODE              | Represents the general node with attributes like serial nr, etc.                            |
| 0x02 | 1             | COMFOBUS          | Unit responsible for comfobus-communication. Probably stores the ID's of connected devices. |
| 0x03 | 1             | ERROR             | Stores errors, allows errors to be reset                                                    |
| 0x15 | 10            | SCHEDULE          | Responsible for managing Timers, the schedule, etc. Check here for level, bypass etc.       |
| 0x16 | 2             | VALVE             | The valves: `01` extract (V11), `02` bypass/preheater (V21) †                               |
| 0x17 | 2             | FAN               | Represents the two fans: `01` exhaust (F12), `02` supply (F22) †                            |
| 0x18 | 1             | POWERSENSOR       | Counts the actual wattage of ventilation and accumulates to year and since factory reset    |
| 0x19 | 1             | PREHEATER         | Represents the optional preheater                                                           |
| 0x1A | 1             | HMI               | Represents the Display + Buttons                                                            |
| 0x1B | 1             | RFCOMMUNICATION   | Wireless-communication with attached devices                                                |
| 0x1C | 1             | FILTER            | Counts the days since last filter change                                                    |
| 0x1D | 1             | TEMPHUMCONTROL    | Controls the target temperature, if its cooling or heating period and some settings         |
| 0x1E | 1             | VENTILATIONCONFIG | Responsible for managing various configuration options of the ventilation                   |
| 0x20 | 1             | NODECONFIGURATION | Manages also some options                                                                   |
| 0x21 | 6             | TEMPERATURESENSOR | Represents the 6 temperature sensors in the ventilation (see below)                         |
| 0x22 | 6             | HUMIDITYSENSOR    | Represents the 6 humidity sensors (see below)                                               |
| 0x23 | 2             | PRESSURESENSOR    | Represents both pressure sensors: `01` exhaust (P12), `02` supply (P22) †                   |
| 0x24 | 1             | PERIPHERALS       | Stores the ID of the ComfoCool attached, can reset peripheral errors here                   |
| 0x25 | 4             | ANALOGINPUT       | Provides data and functionality for the analog inputs, also the scaling for the voltages. Subunit `00` holds the settings the inputs share † |
| 0x26 | 1             | COOKERHOOD        | "Dummy" unit, probably represents the ComfoHood if attached                                 |
| 0x27 | 1             | POSTHEATER        | Represents the optional post heater attached (temperature sens, config)                     |
| 0x28 | 1             | COMFOFOND         | "Dummy" unit, represents the optional comfofond                                             |
| 0x29 | 1             | ERRORLOGGING      | The error log: the number of entries and the entries themselves †                           |
| 0x2A | 1             | COMPONENTCHECK    | The component check of the service menu (fan, bypass, preheater, …) †                       |
| 0x2B | 8             | CO2SENSOR         | The CO2 control, one subunit per zone (`01`-`08`); subunit `00` holds the shared settings † |
| 0x2C | 1             | SERVICEPRINT      | Countries and article numbers, for installing the unit as another article †                 |

The subunits of the sensor units are the same for temperature (T) and humidity (H) †:

| SubUnit | Sensor                                   |
|---------|------------------------------------------|
| 0x01    | Room (T10, H10)                          |
| 0x02    | Extract air (T11, H11)                   |
| 0x03    | Exhaust air (T12, H12)                   |
| 0x04    | Outdoor air (T20, H20)                   |
| 0x05    | Outdoor air after the preheater (T21, H21) |
| 0x06    | Supply air (T22, H22)                    |

Their PDOs follow the same order: `272 + subunit` for the temperatures and `288 + subunit` for the humidities (see
[PROTOCOL-PDO.md](PROTOCOL-PDO.md)).

### Units of other nodes †

Other nodes reuse the unit ids from `0x15` on for their own units (like the ComfoClime below). The app knows these:

| Node (productId)                  | Unit | Name                                                                                       |
|-----------------------------------|------|--------------------------------------------------------------------------------------------|
| ComfoCool (`6`)                   | 0x15 | The cooler                                                                                 |
| ComfoCool (`6`)                   | 0x16 | Temperature sensors: `01` room (T10), `02` condensor (T13), `03` supply air (T23)          |
| Option Box (`4`)                  | 0x15 | Inputs and outputs                                                                         |
| ComfoAir Flex connection board (`9`) | 0x15 | Inputs and outputs                                                                      |
| ComfoAir Flex connection board (`9`) | 0x16 | Node configuration                                                                      |
| ComfoAir Flex connection board (`9`) | 0x17 | WiFi                                                                                    |
| CO2 sensor (`10`)                 | 0x15 | CO2 sensor; property `03` (BOOL, rw) enables it                                            |
| CO2 sensor (`10`)                 | 0x16 | Temperature sensor; property `03` (BOOL, rw) enables it                                    |
| CO2 sensor (`10`)                 | 0x17 | Humidity sensor; property `03` (BOOL, rw) enables it                                       |
| CO2 sensor (`10`)                 | 0x18 | Ambient pressure sensor; property `03` (BOOL, rw) enables it                               |
| CO2 sensor (`10`)                 | 0x19 | Display: property `02` (UINT8, rw) is the LED mode (0=off, 1=warning only, 2=low, 3=medium, 4=high, 5=highest) |

A CO2 sensor also has a property `0E` (BOOL, rw) on its NODE unit, which the app calls the sensor mode.

## Error codes

If an error occurs the reason can be one of the following:

| Number | Description                                 |
|--------|---------------------------------------------|
| 11     | Unknown Command                             |
| 12     | Unknown Unit                                |
| 13     | Unknown SubUnit                             |
| 14     | Unknown property                            |
| 15     | Type can not have a range                   |
| 30     | Value given not in Range                    |
| 32     | Property not gettable or settable           |
| 40     | Internal error                              |
| 41     | Internal error, maybe your command is wrong |

## General commands

There are three commands which always exist on a given Unit:

- `0x01`: Get a single property

  This command reads a single property identified by the Unit, SubUnit and Property.

  Syntax: `01 Unit SubUnit Type Property`

  The `Type` can be one of the following:
  - 0x00: None
  - 0x10: Actual value
  - 0x20: Range
  - 0x40: Step size

  Each writable property may have a range & step size. You can get those values by using the `0x20` and `0x40` `Type` values. You can request multiple types
  at the same time by OR'ing the value.

  Example: Request: `01 1d 01 70 03`, Response: `a0 00 96 00 90 01 0a 00`
  This gets the actual value, the range and the step size of the RMOT cooling threshold (an INT16) at once: 160 (16.0 °C), range 150 - 400, step 10.

  Reading the range and the step size together with the value costs no extra request.

  Example: Request: `01 20 01 10 03`, Response: `34 32 31 30 00` (4210\0)
  This gets the maintainer password. Unit is `NODECONFIGURATION`, SubUnit is `01`, get the actual value, Property `03`.

- `0x02`: Get multiple properties

  This command allows to read multiple properties in one request.

  Syntax: `02 Count Unit SubUnit Type Property1 Property2 ... PropertyN [Unit SubUnit Type Property1 ...]` †

  `Count` is the number of Unit/SubUnit groups that follow, so one request can read properties from several units at
  once. In each group, the `Type` value needs to be OR'ed with the number of properties of that group. So if you want
  to read the actual value of 5 properties, the `Type` value needs to be `0x10 | 0x05` = `0x15`. The official app puts
  at most 7 properties in a group. The response holds the values one after the other, in the order of the request.

  This document used to give the syntax as `02 Unit SubUnit 01 Type ...`. That reads the same bytes for the example
  below, because it reads one group (`Count` = `01`) from Unit `01`, SubUnit `01`, but for any other unit the order
  above is the one the official app uses †.

  Example: Request: `02 01 01 01 15 03 04 06 05 14`, Response: `\02 BEA000000000000\00 \00\10\10\c0 \02 ComfoAirQ\00`
  This reads the following property values of the NODE unit (the same ones the official app reads to identify a node):
    - 0x03: Product variant (`02` is a ComfoAir Q450) †
    - 0x04: Serial Number
    - 0x06: Firmware version
    - 0x05: Hardware version †
    - 0x14: Ventilation Unit Name

- `0x03`: Set a single property

  This commands sets one property to the given value. The value needs to be in the range as identified within 0x01, otherwise an error of 30 is returned. The
  step size, however, is not checked.

  Syntax: `03 Unit SubUnit Property Value`

  Example: `03 1D 01 04 00`
  Unit is `TEMPHUMCONTROL`, SubUnit `01`, Property: `04`, value `00`
  Sets the Property "Sensor ventilation: Temperature passive" to off

Property `0x01` of every unit is the zone of the node (UINT8, rw) †. It is a bit set: zone 1 is `01`, zone 2 is `02`,
zone 3 is `04`, and so on up to zone 8 (`80`); the ComfoConnect LAN C reports `ff` (every zone). That is why so many
units answer `01` for property `0x01` in the tables below.

All other commands are >= `0x80` and dependent on the SubUnit. Please do not try to run command `0x80`, `0x82` on NODECONFIGURATION (`0x20`), they will probably
break your configuration, and even worse would be calling ANY >= `0x80` command on NODE (`0x01`). It can probably completely brick your ventilation. (It enters
factory mode or tries to perform an update.)

### Known properties for Node 0x01 (Ventilation Unit)

Where this table had no access or format, or one that differs from the official app, the Access and Format columns now
follow the app †.

| Unit              | SubUnit | Property | Access | Format | Description                                                            |
|-------------------|---------|----------|--------|--------|------------------------------------------------------------------------|
| NODE              | 0x01    | 0x01     | rw     | UINT8  | Zone (bit set, see above) †; `01` = 1                                  |
| NODE              | 0x01    | 0x02     | ro     | UINT8  | Product id (`01` = 1, ComfoAir Q) †                                    |
| NODE              | 0x01    | 0x03     | ro     | UINT8  | Product variant †: ComfoAir Q 1=Q350, 2=Q450, 3=Q600; ComfoAir Flex 1=250 (85 W), 2=350 (115 W), 3=350 (85 W). `02` = 2 |
| NODE              | 0x01    | 0x04     | ro     | STRING | Serial number (BEA009999999999)                                        |
| NODE              | 0x01    | 0x05     | ro     | UINT8  | Hardware version † (`02` = 2)                                          |
| NODE              | 0x01    | 0x06     | ro     | UINT32 | Firmware version (See `version_decode()`)                              |
| NODE              | 0x01    | 0x07     | ro     | UINT32 | Version of the object definitions, encoded like the firmware version † (`00541040`) |
| NODE              | 0x01    | 0x08     | ro     | STRING | Model number (ComfoAir Q450 B R RF ST Quality)                         |
| NODE              | 0x01    | 0x09     | ro     | UINT32 | Version of the configuration data, encoded like the firmware version † (`04000000`) |
| NODE              | 0x01    | 0x0A     | ro     | UINT32 | Version of the language data, encoded like the firmware version † (`0004f0c0`) |
| NODE              | 0x01    | 0x0B     | ro     | STRING | Article number (471502004)                                             |
| NODE              | 0x01    | 0x0C     | ro     | STRING | Product serial number † (NULL)                                         |
| NODE              | 0x01    | 0x0D     | ro     | STRING | Current Country (BE)                                                   |
| NODE              | 0x01    | 0x14     | rw     | STRING | Ventilation Unit Name (ComfoAirQ); writable according to the app †     |
| FILTER            | 0x01    | 0x02     | rw     | UINT16 | Filter warning period in days (21); a UINT16 in the app †              |
| FILTER            | 0x01    | 0x03     | rw     | UINT16 | Filter lifetime in days (150); the app only uses it from firmware R1.9.0 on † |
| TEMPHUMCONTROL    | 0x01    | 0x01     | rw     | UINT8  | Zone † (`01` = 1)                                                      |
| TEMPHUMCONTROL    | 0x01    | 0x02     | rw     | INT16  | RMOT for heating period (180 -> 18°C)                                  |
| TEMPHUMCONTROL    | 0x01    | 0x03     | rw     | INT16  | RMOT for cooling period (200 -> 20°C)                                  |
| TEMPHUMCONTROL    | 0x01    | 0x04     | rw     | UINT8  | Passive temperature control (0=off, 1=autoonly, 2=on)                  |
| TEMPHUMCONTROL    | 0x01    | 0x05     | rw     | UINT8  | Active temperature control (0=off, 1=autoonly, 2=on) † (`00` = 0)      |
| TEMPHUMCONTROL    | 0x01    | 0x06     | rw     | UINT8  | Humidity comfort control (o=off, 1=autoonly, 2=on)                     |
| TEMPHUMCONTROL    | 0x01    | 0x07     | rw     | UINT8  | Humidity protection (0=off, 1=autoonly, 2=on)                          |
| TEMPHUMCONTROL    | 0x01    | 0x08     | rw     | UINT8  | Temperature profile mode (0=adaptive, 1=fixed; a ComfoAir Q reports a range of 0-1) |
| TEMPHUMCONTROL    | 0x01    | 0x0A     | rw     | INT16  | Target temperature for profile: Heating (230 -> 23°C)                  |
| TEMPHUMCONTROL    | 0x01    | 0x0B     | rw     | INT16  | Target temperature for profile: Normal (210 -> 21°C)                   |
| TEMPHUMCONTROL    | 0x01    | 0x0C     | rw     | INT16  | Target temperature for profile: Cooling (190 -> 19°C)                  |
| TEMPHUMCONTROL    | 0x01    | 0x0D     | rw     | UINT8  | Temperature unit (0=Celsius, 1=Fahrenheit) † (`00` = 0)                |
| TEMPHUMCONTROL    | 0x01    | 0x0E     | rw     | UINT8  | Speed of the passive temperature control (0=slow, 1=medium, 2=fast), from firmware R1.9.0 on † |
| VENTILATIONCONFIG | 0x01    | 0x01     | rw     | UINT8  | Zone † (`01` = 1)                                                      |
| VENTILATIONCONFIG | 0x01    | 0x02     | ro     | UINT8  | Flags of the allowed presets † (`0f` = 15)                             |
| VENTILATIONCONFIG | 0x01    | 0x03     | rw     | INT16  | Ventilation speed in "Away" Level (75); a UINT16 in the app †          |
| VENTILATIONCONFIG | 0x01    | 0x04     | rw     | INT16  | Ventilation speed in "Low" Level (110); a UINT16 in the app †          |
| VENTILATIONCONFIG | 0x01    | 0x05     | rw     | INT16  | Ventilation speed in "Medium" Level (180); a UINT16 in the app †       |
| VENTILATIONCONFIG | 0x01    | 0x06     | rw     | INT16  | Ventilation speed in "High" Level (370); a UINT16 in the app †         |
| VENTILATIONCONFIG | 0x01    | 0x07     | rw     | UINT8  | Height above sea level (0=0-500, 1=500-1000, 2=1000-1500, 3=1500-2000) |
| VENTILATIONCONFIG | 0x01    | 0x08     | ro     | UINT16 | Measured maximum flow † (`8b01` = 395)                                 |
| VENTILATIONCONFIG | 0x01    | 0x09     | rw     | UINT8  | Ventilation control mode (0=flow control, 1=constant flow)             |
| VENTILATIONCONFIG | 0x01    | 0x0A     | rw     | INT16  | Unbalance in direct fan control (DFC) mode, in 0.1 % † (`ecff` = -20 -> -2.0 %) |
| VENTILATIONCONFIG | 0x01    | 0x0B     | rw     | UINT16 | Bathroom switch, activation delay (`300` = 300 sec)                    |
| VENTILATIONCONFIG | 0x01    | 0x0C     | rw     | UINT8  | Bathroom switch, deactivation delay (`30` = 30 min)                    |
| VENTILATIONCONFIG | 0x01    | 0x0D     | rw     | UINT8  | Bathroom switch, mode (0=fixed, 1=mirrored)                            |
| VENTILATIONCONFIG | 0x01    | 0x0E     | rw     | UINT8  | Airflow unit (1=kg/h, 2=l/s, 3=m³/h) † (`03` = 3)                      |
| VENTILATIONCONFIG | 0x01    | 0x0F     | rw     | BOOL   | Direct fan control (DFC) enabled † (`00` = 0)                          |
| VENTILATIONCONFIG | 0x01    | 0x11     | rw     | UINT16 | Flow in direct fan control (DFC) mode † (`c800` = 200)                 |
| VENTILATIONCONFIG | 0x01    | 0x12     | rw     | INT16  | Unbalance (`9dff` = -99 -> -9.9 %)                                     |
| VENTILATIONCONFIG | 0x01    | 0x13     | ro     | UINT16 | Maximum reference flow, exhaust fan † (`0000` = 0)                     |
| VENTILATIONCONFIG | 0x01    | 0x14     | ro     | UINT16 | Maximum reference flow, supply fan † (`0000` = 0)                      |
| VENTILATIONCONFIG | 0x01    | 0x15     | ro     | UINT16 | Maximum reference fan speed, exhaust fan † (`980d` = 3480)             |
| VENTILATIONCONFIG | 0x01    | 0x16     | ro     | UINT16 | Maximum reference fan speed, supply fan † (`660c` = 3174)              |
| VENTILATIONCONFIG | 0x01    | 0x17     | ro     | UINT16 | Medium reference flow, exhaust fan † (`0000` = 0)                      |
| VENTILATIONCONFIG | 0x01    | 0x18     | ro     | UINT16 | Medium reference flow, supply fan † (`0000` = 0)                       |
| VENTILATIONCONFIG | 0x01    | 0x19     | ro     | UINT16 | Medium reference fan speed, exhaust fan † (`8107` = 1921)              |
| VENTILATIONCONFIG | 0x01    | 0x1A     | ro     | UINT16 | Medium reference fan speed, supply fan † (`a106` = 1697)               |
| VENTILATIONCONFIG | 0x01    | 0x1B     | ro     | UINT16 | Fan speed at maximum pressure, exhaust fan † (`0f05` = 1295)           |
| VENTILATIONCONFIG | 0x01    | 0x1C     | ro     | UINT16 | Fan speed at maximum pressure, supply fan † (`0c05` = 1292)            |
| VENTILATIONCONFIG | 0x01    | 0x1D     | ro     | UINT16 | Expected fan speed without pressure, exhaust fan † (`5304` = 1107)     |
| VENTILATIONCONFIG | 0x01    | 0x1E     | ro     | UINT16 | Expected fan speed without pressure, supply fan † (`1304` = 1043)      |
| VENTILATIONCONFIG | 0x01    | 0x1F     | ro     | UINT16 | Expected maximum flow †                                                |
| VENTILATIONCONFIG | 0x01    | 0x20     | rw     | UINT8  | ComfoHood switch-off delay, from firmware R1.5.0 on †                  |
| NODECONFIGURATION | 0x01    | 0x01     | rw     | UINT8  | Zone † (`01` = 1)                                                      |
| NODECONFIGURATION | 0x01    | 0x03     | ro     | STRING | Maintainer password (NL=4210, BE=2468, DE=4210); 4 characters †        |
| NODECONFIGURATION | 0x01    | 0x04     | ro     | BOOL   | ComfoSense allowed †. This table listed the orientation here before; the app reads it from `0x06` |
| NODECONFIGURATION | 0x01    | 0x05     | ro     | BOOL   | ComfoSwitch allowed † (`01` = 1)                                       |
| NODECONFIGURATION | 0x01    | 0x06     | rw     | UINT8  | Orientation (0=left, 1=right) † (`00` = 0)                             |
| NODECONFIGURATION | 0x01    | 0x07     | rw     | UINT8  | Position of the condensation drain (0=none, 1=left, 2=right) † (`00` = 0) |
| NODECONFIGURATION | 0x01    | 0x08     | rw     | BOOL   | Fireplace present † (`01` = 1)                                         |
| NODECONFIGURATION | 0x01    | 0x0A     | rw     | UINT8  | User level of the menu (0=basic, 1=advanced, 2=installer) † (`00` = 0) |
| NODECONFIGURATION | 0x01    | 0x0B     | rw     | UINT8  | Preset used to fine tune the airflow (0=away, 1=low, 2=medium, 3=high) † (`02` = 2) |
| NODECONFIGURATION | 0x01    | 0x0C     | rw     | BOOL   | Commissioning finished † (`01` = 1)                                    |
| NODECONFIGURATION | 0x01    | 0x0D     | rw     | UINT8  | Heat recovery type (0=HRV, 1=ERV), from firmware R1.5.0 on †           |

### Other properties of the ventilation unit †

The app also reads and writes these properties. None of them were checked on a unit.

| Unit              | SubUnit   | Property | Access | Format | Description                                                              |
|-------------------|-----------|----------|--------|--------|--------------------------------------------------------------------------|
| COMFOBUS          | 0x01      | 0x02     | ro     | BOOL   | The CAN bus is off                                                       |
| COMFOBUS          | 0x01      | 0x03     | ro     | UINT8  | CAN receive error counter                                                |
| COMFOBUS          | 0x01      | 0x04     | ro     | UINT8  | CAN transmit error counter                                               |
| VALVE             | 0x01-0x02 | 0x02     | rw     | UINT16 | Valve position, in 0.1 %                                                 |
| FAN               | 0x01-0x02 | 0x02     | ro     | BOOL   | The fan may be disabled                                                  |
| PREHEATER         | 0x01      | 0x02     | ro     | BOOL   | Preheater present                                                        |
| PREHEATER         | 0x01      | 0x03     | ro     | UINT8  | Location of the preheater (0=left, 1=right)                              |
| PREHEATER         | 0x01      | 0x04     | rw     | UINT8  | Duty cycle, in %                                                         |
| PREHEATER         | 0x01      | 0x05     | rw     | UINT8  | Ratio, in %                                                              |
| HMI               | 0x01      | 0x02     | ro     | BOOL   | Display present                                                          |
| HMI               | 0x01      | 0x03     | rw     | UINT8  | Brightness                                                               |
| HMI               | 0x01      | 0x04     | rw     | STRING | Language                                                                 |
| HMI               | 0x01      | 0x05     | rw     | BOOL   | Child lock                                                               |
| HMI               | 0x01      | 0x06     | rw     | UINT8  | Door state (also PDO 162)                                                |
| HMI               | 0x01      | 0x07     | rw     | UINT8  | Button states (also PDO 161)                                             |
| HMI               | 0x01      | 0x08     | ro     | BOOL   | LCD operational (also PDO 160)                                           |
| RFCOMMUNICATION   | 0x01      | 0x02     | ro     | BOOL   | RF present                                                               |
| RFCOMMUNICATION   | 0x01      | 0x03     | ro     | BOOL   | RF enabled                                                               |
| RFCOMMUNICATION   | 0x01      | 0x04     | rw     | UINT8  | Priority of RF sensors (0=on, 1=autoonly, 2=off)                         |
| RFCOMMUNICATION   | 0x01      | 0x05     | rw     | UINT8  | Function of RF sensors (0=flow proportional, 1=flow preset)              |
| RFCOMMUNICATION   | 0x01      | 0x06     | rw     | UINT8  | RF duty, in %                                                            |
| TEMPERATURESENSOR | 0x01-0x06 | 0x02     | ro     | BOOL   | Sensor present                                                           |
| HUMIDITYSENSOR    | 0x01-0x06 | 0x02     | ro     | BOOL   | Sensor present                                                           |
| PRESSURESENSOR    | 0x01-0x02 | 0x02     | ro     | BOOL   | Sensor present                                                           |
| PERIPHERALS       | 0x01      | 0x0B     | ro     | UINT8  | The ComfoCool that is attached                                           |
| ANALOGINPUT       | 0x00      | 0x01     | rw     | UINT8  | Priority of the analog inputs (0=on, 1=autoonly, 2=off)                  |
| ANALOGINPUT       | 0x00      | 0x02     | rw     | UINT8  | Function of the analog inputs (0=flow proportional, 1=flow preset)       |
| ANALOGINPUT       | 0x00      | 0x03     | ro     | BOOL   | Analog inputs present                                                    |
| ANALOGINPUT       | 0x01-0x04 | 0x02     | rw     | UINT8  | Level for 0 %                                                            |
| ANALOGINPUT       | 0x01-0x04 | 0x03     | rw     | UINT8  | Level for 100 %                                                          |
| ANALOGINPUT       | 0x01-0x04 | 0x04     | rw     | UINT8  | Mode (0=steer, 1=control)                                                |
| ANALOGINPUT       | 0x01-0x04 | 0x05     | rw     | UINT8  | Setpoint in control mode                                                 |
| ANALOGINPUT       | 0x01-0x04 | 0x06     | rw     | UINT8  | Proportional band in control mode, in % (0-255)                          |
| ANALOGINPUT       | 0x01-0x04 | 0x07     | rw     | UINT16 | Integral time in control mode                                            |
| ANALOGINPUT       | 0x01-0x04 | 0x08     | rw     | BOOL   | Input enabled                                                            |
| POSTHEATER        | 0x01      | 0x03     | rw     | INT16  | Proportional band                                                        |
| POSTHEATER        | 0x01      | 0x04     | rw     | UINT16 | Integral time                                                            |
| POSTHEATER        | 0x01      | 0x05     | rw     | INT16  | Comfort temperature, in 0.1 °C                                           |
| CO2SENSOR         | 0x00      | 0x01     | rw     | UINT8  | Priority of the CO2 control (0=on, 1=autoonly, 2=off)                    |
| CO2SENSOR         | 0x00      | 0x02     | rw     | UINT8  | Function of the CO2 control (0=flow proportional, 1=flow preset)         |
| CO2SENSOR         | 0x01-0x08 | 0x02     | rw     | UINT16 | Level for 0 %                                                            |
| CO2SENSOR         | 0x01-0x08 | 0x03     | rw     | UINT16 | Level for 100 %                                                          |
| CO2SENSOR         | 0x01-0x08 | 0x05     | rw     | UINT16 | Setpoint in control mode                                                 |
| CO2SENSOR         | 0x01-0x08 | 0x06     | rw     | UINT8  | Proportional band in control mode, in % (0-250)                          |
| CO2SENSOR         | 0x01-0x08 | 0x07     | rw     | UINT16 | Integral time in control mode                                            |
| CO2SENSOR         | 0x01-0x08 | 0x08     | rw     | BOOL   | CO2 control of the zone enabled                                          |

On subunit `00` of ANALOGINPUT and CO2SENSOR, the app reads property `0x01` as the priority, not as the zone.

### Known properties for Node 0x30 (ComfoConnect LAN C)

| Unit              | SubUnit | Property | Access | Format | Description                                                            |
|-------------------|---------|----------|--------|--------|------------------------------------------------------------------------|
| NODE              | 0x01    | 0x01     | rw     | UINT8  | Zone † (`ff` = 255, every zone)                                        |
| NODE              | 0x01    | 0x02     | ro     | UINT8  | Product id † (`05` = 5, Zehnder gateway)                               |
| NODE              | 0x01    | 0x03     | ro     | UINT8  | Product variant † (`00` = 0)                                           |
| NODE              | 0x01    | 0x04     | ro     | STRING | Serial number (DEM0999999999)                                          |
| NODE              | 0x01    | 0x05     | ro     | UINT8  | Hardware version † (`01` = 1)                                          |
| NODE              | 0x01    | 0x06     | ro     | UINT32 | Firmware version (See `version_decode()`)                              |
| NODE              | 0x01    | 0x07     | ro     | UINT32 | Version of the object definitions, encoded like the firmware version † (`008c10c0`) |
| NODE              | 0x01    | 0x14     | ro     | STRING | Unit Name (ComfoConnect LAN C)                                         |

### Known properties for a ComfoClime node (productId 0x14)

The ComfoClime reuses unit ids `0x16` and `0x17` for its own purposes, so these are *not* the VALVE and FAN
units of a ventilation unit. Reverse engineered from the ComfoClime's own HTTP API, which addresses these as
`unit/subunit/property`. All temperatures are stored in tenths of a degree.

| Unit              | SubUnit | Property | Access | Format | Description                                                            |
|-------------------|---------|----------|--------|--------|------------------------------------------------------------------------|
| NODE              | 0x01    | 0x04     | ro     | STRING | Serial number (MBE0999999999)                                          |
| NODE              | 0x01    | 0x06     | ro     | UINT32 | Firmware version (See `version_decode()`)                              |
| NODE              | 0x01    | 0x14     | rw     | STRING | Unit Name                                                              |
| CLIME_TEMPCONFIG  | 0x01    | 0x02     | rw     | UINT8  | Automatic season detection (0=off, 1=on)                               |
| CLIME_TEMPCONFIG  | 0x01    | 0x03     | rw     | UINT8  | Season (0=transition, 1=heating, 2=cooling)                            |
| CLIME_TEMPCONFIG  | 0x01    | 0x04     | rw     | INT16  | Heating curve knee point (5.0 - 15.0 °C)                               |
| CLIME_TEMPCONFIG  | 0x01    | 0x05     | rw     | INT16  | Cooling curve knee point (15.0 - 25.0 °C)                              |
| CLIME_TEMPCONFIG  | 0x01    | 0x09     | rw     | INT16  | Heating comfort temperature (15.0 - 25.0 °C)                           |
| CLIME_TEMPCONFIG  | 0x01    | 0x0A     | rw     | INT16  | Cooling comfort temperature (20.0 - 28.0 °C)                           |
| CLIME_TEMPCONFIG  | 0x01    | 0x0B     | rw     | INT16  | Maximum temperature while cooling (20.0 - 28.0 °C)                     |
| CLIME_TEMPCONFIG  | 0x01    | 0x0C     | rw     | INT16  | Heating reduction delta (0.0 - 5.0 °C)                                 |
| CLIME_TEMPCONFIG  | 0x01    | 0x0D     | rw     | INT16  | Manual target temperature (18.0 - 28.0 °C)                             |
| CLIME_TEMPCONFIG  | 0x01    | 0x15     | rw     | UINT8  | Heat pump standby (0=active, 1=standby)                               |
| CLIME_TEMPCONFIG  | 0x01    | 0x1D     | rw     | UINT8  | Temperature profile (0=comfort, 1=power, 2=eco)                        |
| CLIME_HEATPUMP    | 0x01    | 0x03     | rw     | INT16  | Heat pump maximum temperature (40.0 - 60.0 °C)                         |
| CLIME_HEATPUMP    | 0x01    | 0x04     | rw     | INT16  | Heat pump minimum temperature (10.0 - 17.0 °C)                         |

The ComfoClime also drives two properties on the ventilation unit node:

| Unit              | SubUnit | Property | Access | Format | Description                                                            |
|-------------------|---------|----------|--------|--------|------------------------------------------------------------------------|
| TEMPHUMCONTROL    | 0x01    | 0x02     | rw     | INT16  | RMOT heating threshold (5.0 - 20.0 °C)                                 |
| TEMPHUMCONTROL    | 0x01    | 0x03     | rw     | INT16  | RMOT cooling threshold (5.0 - 35.0 °C)                                 |

## SCHEDULE Unit commands

- `0x80`: GETSCHEDULEENTRY
- `0x81`: ENABLESCHEDULEENTRY
- `0x82`: DISABLESCHEDULEENTRY
- `0x83`: GETTIMERENTRY
- `0x84`: ENABLETIMERENTRY
- `0x85`: DISABLETIMERENTRY
- `0x86`: GETSCHEDULE
- `0x87`: GETTIMERS

### Known schedules

Each subunit has one or more timers that override a setting. The request is `command subunit timer`:

- `0x83 subunit timer`: get the timer. Reply: `active(u8) delay(i32) duration(i32) remaining(i32) value(u8)`. An inactive timer keeps the fields of its last run, so only use them when `active` is `01`.
- `0x84 subunit timer delay(i32) duration(i32) value(u8)`: start the timer. A duration of `-1` runs until it is cancelled. A duration of `1` lets the unit pick its default (the speed and manual mode timers use this, like the official app).
- `0x85 subunit timer`: cancel the timer. The official app cancels all timers of a subunit at once with timer `00` †.
- `0x87 subunit`: get all timers of the subunit †. Reply: one byte, then the 14 bytes of the `0x83` reply for every
  timer of the subunit, from timer 1 on.

The constants are in `aiocomfoconnect/const.py`, and `ComfoConnect` has `get_timer`, `set_timer` and `cancel_timer`.

| SubUnit | Timer | Constants                                       | Description                                           |
|:--------|-------|-------------------------------------------------|-------------------------------------------------------|
| 0x01    | 0x01  | `SCHEDULE_PRESET`, `TIMER_DEFAULT`              | Fan speed (`00`=away/`01`=low/`02`=medium/`03`=high)  |
| 0x01    | 0x02  |                                                 | PRESETRF                                              |
| 0x01    | 0x03  |                                                 | PRESETANALOG                                          |
| 0x01    | 0x04  |                                                 | PRESETRFANALOG                                        |
| 0x01    | 0x05  |                                                 | MANUALMODE                                            |
| 0x01    | 0x06  | `SCHEDULE_PRESET`, `TIMER_BOOST`                | Boost (`03`=high)                                     |
| 0x01    | 0x07  |                                                 | BOOSTRF                                               |
| 0x01    | 0x08  |                                                 | BOOSTSWITCH                                           |
| 0x01    | 0x0b  | `SCHEDULE_PRESET`, `TIMER_AWAY`                 | Away (`00`=away)                                      |
| 0x02    | 0x01  | `SCHEDULE_BYPASS`, `TIMER_DEFAULT`              | Bypass (`01`=on/`02`=off, no timer is auto)           |
| 0x03    | 0x01  | `SCHEDULE_TEMPERATURE_PROFILE`, `TIMER_DEFAULT` | Temperature profile (`00`=normal/`01`=cool/`02`=warm) |
| 0x04    | 0x01  |                                                 | Standby (`00`=off/`01`=on) †                          |
| 0x05    | 0x01  | `SCHEDULE_COMFOCOOL`, `TIMER_DEFAULT`           | ComfoCool (`00`=auto/`01`=off in the official app)    |
| 0x06    | 0x01  | `SCHEDULE_SUPPLY_ONLY`, `TIMER_DEFAULT`         | Exhaust fan off (`01`), so supply only                |
| 0x07    | 0x01  | `SCHEDULE_EXHAUST_ONLY`, `TIMER_DEFAULT`        | Supply fan off (`01`), so exhaust only                |
| 0x08    | 0x01  | `SCHEDULE_MANUAL_MODE`, `TIMER_DEFAULT`         | Manual mode (`01`=manual, no timer is auto)           |
| 0x09    | 0x01  |                                                 | ComfoHood (`00`=off/`01`=on) †                        |
| 0x09    | 0x02  |                                                 | ComfoHood switch timer (`00`=off/`01`=on) †           |
| 0x0a    | 0x01  |                                                 | Postheater (`00`=off/`01`=heat/`02`=comfort) †        |

The durations the official app offers for a timer are 1, 2, 3, 6 and 12 hours and 1 day; for the ComfoCool and for
supply fan off (exhaust only) also "continuous", a duration of `-1` †.

### Week schedule †

Next to the timers, every subunit has a week schedule of 10 entries. The official app reads and writes it like this:

- `0x86 subunit`: get the whole schedule. Reply: 130 bytes, 13 bytes for each of the 10 entries.
- `0x80 subunit entry`: get one entry. Reply: the 13 bytes of that entry.
- `0x81 subunit entry day hour minute duration(i32) value(u8)`: enable an entry. The app leaves entry `00` alone and
  adds new entries in the first free slot from `01` to `09`.
- `0x82 subunit entry`: disable an entry.

An entry is `enabled(u8) day(u8) hour(u8) minute(u8) duration(i32) remaining(i32) value(u8)`: the entry starts at
`hour:minute`, lasts `duration` seconds (the app adds a day when the end time is earlier than the start time) and sets
the subunit to `value`, with the same values as the timers. When `enabled` is not `01` the rest of the entry has no
meaning. The days are: `00`=every day, `01`=Monday to `07`=Sunday, `08`=weekdays, `09`=weekend, `0a`=no day.

The PDOs with base 32 and 320 report the active entry and the enabled entries (see
[Schedule PDOs](PROTOCOL-PDO.md#schedule-pdos)).

## ERROR Unit commands

- `0x80`: GETACTIVEERRORS. The reply is a bit set of 32 bytes: bit `n` is set when error `n` is active †.
- `0x82`: RESETALLERRORS

### Error list

| Error ID | Description                                                                                                                                       |
|:---------|---------------------------------------------------------------------------------------------------------------------------------------------------|
| 21       | DANGER! OVERHEATING! Two or more sensors are detecting an incorrect temperature. Ventilation has stopped.                                         | 
| 22       | Temperature too high for ComfoAir Q (TEMP_HRU ERROR)                                                                                              | 
| 23       | The extract air temperature sensor has a malfunction (SENSOR_ETA ERROR)                                                                           | 
| 24       | The extract air temperature sensor is detecting an incorrect temperature (TEMP_SENSOR_ETA ERROR)                                                  | 
| 25       | The exhaust air temperature sensor has a malfunction (SENSOR_EHA ERROR)                                                                           | 
| 26       | The exhaust air temperature sensor is detecting an incorrect temperature (TEMP_SENSOR_EHA ERROR)                                                  | 
| 27       | The outdoor air temperature sensor has a malfunction (SENSOR_ODA ERROR)                                                                           | 
| 28       | The outdoor air temperature sensor is detecting an incorrect temperature (TEMP_SENSOR_ODA ERROR)                                                  | 
| 29       | The pre-conditioned outdoor air temperature sensor has a malfunction                                                                              | 
| 30       | The pre-conditioned outdoor air temperature sensor is detecting an incorrect temperature (TEMP_SENSOR_P-ODA ERROR)                                | 
| 31       | The supply air temperature sensor has a malfunction (SENSOR_SUP ERROR)                                                                            | 
| 32       | The supply air temperature sensor is detecting an incorrect temperature (TEMP_SENSOR_SUP ERROR)                                                   | 
| 33       | The Ventilation Unit has not been commissioned (INIT ERROR)                                                                                       | 
| 34       | The front door is open                                                                                                                            | 
| 35       | The Pre-heater is present, but not in the correct position (right/left). (PREHEAT_LOCATION ERROR)                                                 | 
| 37       | The pre-heater has a malfunction (PREHEAT ERROR)                                                                                                  | 
| 38       | The pre-heater has a malfunction (PREHEAT ERROR)                                                                                                  | 
| 39       | The extract air humidity sensor has a malfunction (SENSOR_ETA ERROR)                                                                              | 
| 41       | The exhaust air humidity sensor has a malfunction (SENSOR_EHA ERROR)                                                                              | 
| 43       | The outdoor air humidity sensor has a malfunction (SENSOR_ODA ERROR)                                                                              | 
| 45       | The outdoor air humidity sensor has a malfunction (SENSOR_P-ODA ERROR)                                                                            | 
| 47       | The supply air humidity sensor has a malfunction (SENSOR_SUP ERROR)                                                                               | 
| 49       | The exhaust air flow sensor has a malfunction (SENSOR_EHA ERROR)                                                                                  | 
| 50       | The supply air flow sensor has a malfunction (SENSOR_SUP ERROR)                                                                                   | 
| 51       | The extract air fan has a malfunction (FAN_EHA ERROR)                                                                                             | 
| 52       | The supply air fan has a malfunction (FAN_SUP ERROR)                                                                                              | 
| 53       | Exhaust air pressure too high. Check air outlets, ducts and filters for pollution and obstructions. Check valve settings (EXT_PRESSURE_EHA ERROR) | 
| 54       | Supply air pressure too high. Check air outlets, ducts and filters for pollution and obstructions. Check valve settings. (EXT_PRESSURE_SUP ERROR) | 
| 55       | The extract air fan has a malfunction (FAN_EHA ERROR)                                                                                             | 
| 56       | The supply air fan has a malfunction (FAN_SUP ERROR)                                                                                              | 
| 57       | The exhaust air flow is not reaching its set point (AIRFLOW_EHA ERROR)                                                                            | 
| 58       | The supply air flow is not reaching its set point (AIRFLOW_SUP ERROR)                                                                             | 
| 59       | Failed to reach required temperature too often for outdoor air after pre-heater (TEMPCONTROL_P-ODA ERROR)                                         | 
| 60       | Failed to reach required temperature too often for supply air. The modulating by-pass may have a malfunction. (TEMPCONTROL_SUP ERROR)             | 
| 61       | Supply air temperature is too low too often (TEMP_SUP_MIN ERROR)                                                                                  | 
| 62       | Unbalance occurred too often beyond tolerance levels in past period (UNBALANCE ERROR)                                                             | 
| 63       | Postheater was present, but is no longer detected (POSTHEAT_CONNECT ERROR)                                                                        | 
| 64       | Temperature sensor value for supply air ComfoCool exceeded limit too often (CCOOL_TEMP ERROR)                                                     | 
| 65       | Room temperature sensor was present, but is no longer detected (T_ROOM_PRES ERROR)                                                                | 
| 66       | RF Communication hardware was present, but is no longer detected (RF_PRES ERROR)                                                                  | 
| 67       | Option Box was present, but is no longer detected (OPTION_BOX CONNECT ERROR)                                                                      | 
| 68       | Pre-heater was present, but is no longer detected (PREHEAT_PRES ERROR)                                                                            | 
| 69       | Postheater was present, but is no longer detected (POSTHEAT_CONNECT ERROR)                                                                        | 
|          |                                                                                                                                                   |
|          | # Firmware 1.4.0+ (the official app uses this numbering for every version except exactly R1.4.0 †)                                              |
| 70       | Analog input 1 was present, but is no longer detected (ANALOG_1_PRES ERROR)                                                                       | 
| 71       | Analog input 2 was present, but is no longer detected (ANALOG_2_PRES ERROR)                                                                       | 
| 72       | Analog input 3 was present, but is no longer detected (ANALOG_3_PRES ERROR)                                                                       | 
| 73       | Analog input 4 was present, but is no longer detected (ANALOG_4_PRES ERROR)                                                                       | 
| 74       | ComfoHood was present, but is no longer detected (HOOD_CONNECT ERROR)                                                                             | 
| 75       | ComfoCool was present, but is no longer detected (CCOOL_CONNECT ERROR)                                                                            | 
| 76       | ComfoFond was present, but is no longer detected (GROUND_HEAT_CONNECT ERROR)                                                                      | 
| 77       | The filters of the Ventilation Unit must be replaced now                                                                                          | 
| 78       | It is necessary to replace or clean the external filter                                                                                           | 
| 79       | Order new filters now, because the remaining filter life time is limited                                                                          | 
| 80       | Service mode is active (SERVICE MODE)                                                                                                             | 
| 81       | Preheater has no communication with the ComfoAir unit (PREHEAT ERROR , 1081)                                                                      | 
| 82       | ComfoHood temperature error (HOOD_TEMP ERROR)                                                                                                     | 
| 83       | Postheater temperature error (POSTHEAT_TEMP ERROR)                                                                                                | 
| 84       | Outdoor temperature of ComfoFond error (GROUND_HEAT_TEMP ERROR)                                                                                   | 
| 85       | Analog input 1 error (ANALOG_1_IN ERROR)                                                                                                          | 
| 86       | Analog input 2 error (ANALOG_2_IN ERROR)                                                                                                          | 
| 87       | Analog input 3 error (ANALOG_3_IN ERROR)                                                                                                          | 
| 88       | Analog input 4 error (ANALOG_4_IN ERROR)                                                                                                          | 
| 89       | Bypass is in manual mode                                                                                                                          | 
| 90       | ComfoCool is overheating                                                                                                                          | 
| 91       | ComfoCool compressor error (CCOOL_COMPRESSOR ERROR)                                                                                               | 
| 92       | ComfoCool room temperature sensor error (CCOOL_TEMP ERROR)                                                                                        | 
| 93       | ComfoCool condensor temperature sensor error (CCOOL_TEMP ERROR)                                                                                   | 
| 94       | ComfoCool supply air temperature sensor error (CCOOL_TEMP ERROR)                                                                                  | 
| 95       | ComfoHood temperature is too high (HOOD_TEMP ERROR)                                                                                               | 
| 96       | ComfoHood is activated                                                                                                                            | 
| 97       | UNKNOWN: QM_Constraint_min_ERR                                                                                                                    |  
| 98       | UNKNOWN: H_21_qm_min_ERR                                                                                                                          |  
| 99       | Configuration error                                                                                                                               | 
| 100      | Error analysis is in progress…                                                                                                                    | 
| 101      | ComfoNet Error                                                                                                                                    | 
| 102      | The number of CO2 sensors has decreased – one or more sensors are no longer detected                                                              | 
| 103      | More than 8 sensors detected in a zone                                                                                                            | 
| 104      | CO₂ Sensor C error                                                                                                                                | 
| 105      | General I²C bus error †                                                                                                                           |
|          |                                                                                                                                                   |
|          | # Firmware 1.4.0 (the official app uses this numbering only for exactly R1.4.0 †)                                                               |
| 70       | ComfoHood was present, but is no longer detected (HOOD_CONNECT ERROR)                                                                             | 
| 71       | ComfoCool was present, but is no longer detected (CCOOL_CONNECT ERROR)                                                                            | 
| 72       | ComfoFond was present, but is no longer detected (GROUND_HEAT_CONNECT ERROR)                                                                      | 
| 73       | The filters of the Ventilation Unit must be replaced now                                                                                          | 
| 74       | It is necessary to replace or clean the external filter                                                                                           | 
| 75       | Order new filters now, because the remaining filter life time is limited                                                                          | 
| 76       | Service mode is active (SERVICE MODE)                                                                                                             | 
| 77       | Preheater has no communication with the ComfoAir unit (PREHEAT ERROR , 1081)                                                                      | 
| 78       | ComfoHood temperature error (HOOD_TEMP ERROR)                                                                                                     | 
| 79       | Postheater temperature error (POSTHEAT_TEMP ERROR)                                                                                                | 
| 80       | Outdoor temperature of ComfoFond error (GROUND_HEAT_TEMP ERROR)                                                                                   | 
| 81       | Bypass is in manual mode                                                                                                                          | 
| 82       | ComfoCool is overheating                                                                                                                          | 
| 83       | ComfoCool compressor error (CCOOL_COMPRESSOR ERROR)                                                                                               | 
| 84       | ComfoCool room temperature sensor error (CCOOL_TEMP ERROR)                                                                                        | 
| 85       | ComfoCool condensor temperature sensor error (CCOOL_TEMP ERROR)                                                                                   | 
| 86       | ComfoCool supply air temperature sensor error (CCOOL_TEMP ERROR)                                                                                  | 

## Commands of other units †

The official app uses these commands of the ventilation unit. Like the warning above says, some of them change the
configuration or the state of the unit, so don't try them on a unit you care about.

| Unit              | Command | Arguments                                   | Description                                                      |
|-------------------|---------|---------------------------------------------|------------------------------------------------------------------|
| NODE              | `0x80`  |                                             | Enter update mode                                                |
| NODE              | `0x81`  |                                             | Enter factory mode                                               |
| NODE              | `0x82`  |                                             | Enter operational mode                                           |
| NODE              | `0x83`  |                                             | Enter service mode                                               |
| NODECONFIGURATION | `0x80`  | which (u8)                                  | Revert to defaults: 0=factory, 1=installer, 2=user without the schedules, 3=user with the schedules |
| NODECONFIGURATION | `0x82`  | event (u8)                                  | Commissioning wizard: 0=abort, 1=finish, 2=stop and save, 3=start |
| FAN               | `0x81`  | one byte                                    | Enable the fan                                                   |
| FAN               | `0x82`  |                                             | Disable the fan                                                  |
| POWERSENSOR       | `0x80`  |                                             | Reset the analysis                                               |
| PREHEATER         | `0x80`  |                                             | Reset the analysis                                               |
| HMI               | `0x80`  |                                             | Get the languages                                                |
| RFCOMMUNICATION   | `0x80`  |                                             | Start pairing an RF device (follow it with PDO 176)              |
| RFCOMMUNICATION   | `0x81`  |                                             | Stop pairing                                                     |
| FILTER            | `0x80`  |                                             | Begin the filter replacement                                     |
| FILTER            | `0x81`  |                                             | End the filter replacement                                       |
| FILTER            | `0x82`  |                                             | Abort the filter replacement                                     |
| FILTER            | `0x83`  |                                             | Reset the days left of the filter                                |
| VENTILATIONCONFIG | `0x80`  |                                             | Set the airflow units                                            |
| PERIPHERALS       | `0x80`  |                                             | Reset the presence of the peripherals                            |
| ERRORLOGGING      | `0x80`  | type (u8): 0=error, 1=assert                | Get the number of log entries                                    |
| ERRORLOGGING      | `0x81`  |                                             | Get a log entry                                                  |
| COMPONENTCHECK    | `0x80`  | component (u8)                              | Start the check of 0=none, 1=fan, 2=bypass, 3=preheater, 4=postheater, 5=ComfoFond, 6=ComfoCool |
| COMPONENTCHECK    | `0x81`  |                                             | Stop the check                                                   |
| COMPONENTCHECK    | `0x82`  |                                             | Reset the timer of the check                                     |
| SERVICEPRINT      | `0x7e`  |                                             | Get the number of countries                                      |
| SERVICEPRINT      | `0x7f`  | index (u8)                                  | Get the name of a country                                        |
| SERVICEPRINT      | `0x80`  | country (string)                            | Get the number of article numbers                                |
| SERVICEPRINT      | `0x81`  | country (string), index (u8)                | Get an article number                                            |
| SERVICEPRINT      | `0x82`  | two strings                                 | Get the description of an article                                |
| SERVICEPRINT      | `0x83`  | two strings                                 | Install an article                                               |

## Example list of commonly-used commands

See the `comfoconnect.py` file for more commands and how they are constructed.

| Command                            | Description                                            |
|------------------------------------|--------------------------------------------------------|
| `84 15 01 01 00000000 01000000 00` | Switch to fan speed away                               |
| `84 15 01 01 00000000 01000000 01` | Switch to fan speed 1                                  |
| `84 15 01 01 00000000 01000000 02` | Switch to fan speed 2                                  |
| `84 15 01 01 00000000 01000000 03` | Switch to fan speed 3                                  |
| `84 15 01 06 00000000 58020000 03` | Boost mode: start for 10m (= 600 seconds = `0x0258`)   |
| `85 15 01 06`                      | Boost mode: end                                        |
| `85 15 08 01`                      | Switch to auto mode                                    |
| `84 15 08 01 00000000 01000000 01` | Switch to manual mode                                  |
| `84 15 06 01 00000000 100e0000 01` | Set ventilation mode: supply only for 1 hour           |
| `85 15 06 01`                      | Set ventilation mode: balance mode                     |
| `84 15 03 01 00000000 ffffffff 00` | Set temperature profile: normal                        |
| `84 15 03 01 00000000 ffffffff 01` | Set temperature profile: cool                          |
| `84 15 03 01 00000000 ffffffff 02` | Set temperature profile: warm                          |
| `84 15 02 01 00000000 100e0000 01` | Set bypass: activated for 1 hour                       |
| `84 15 02 01 00000000 100e0000 02` | Set bypass: deactivated for 1 hour                     |
| `85 15 02 01`                      | Set bypass: auto                                       |
| `03 1d 01 04 00`                   | Set sensor ventilation: temperature passive: off       |
| `03 1d 01 04 01`                   | Set sensor ventilation: temperature passive: auto only |
| `03 1d 01 04 02`                   | Set sensor ventilation: temperature passive: on        |
| `03 1d 01 06 00`                   | Set sensor ventilation: humidity comfort: off          |
| `03 1d 01 06 01`                   | Set sensor ventilation: humidity comfort: auto only    |
| `03 1d 01 06 02`                   | Set sensor ventilation: humidity comfort: on           |
| `03 1d 01 07 00`                   | Set sensor ventilation: humidity protection: off       |
| `03 1d 01 07 01`                   | Set sensor ventilation: humidity protection: auto      |
| `03 1d 01 07 02`                   | Set sensor ventilation: humidity protection: on        |
