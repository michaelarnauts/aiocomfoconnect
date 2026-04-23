# RMI Protocol

## Nodes

A RMI message is send towards a Node. There are two known nodes.

| Node | Description                   |
|------|-------------------------------|
| 0x01 | The Ventilation Unit itself   |
| 0x30 | The ComfoConnect LAN C device |

## Units

The Ventilation Unit is seperated into multiple Units, and sometimes even SubUnits. Here is a list of some existing units:

| ID   | # of SubUnits | Name              | Responsible for                                                                             |
|------|---------------|-------------------|---------------------------------------------------------------------------------------------|
| 0x01 | 1             | NODE              | Represents the general node with attributes like serial nr, etc.                            |
| 0x02 | 1             | COMFOBUS          | Unit responsible for comfobus-communication. Probably stores the ID's of connected devices. |
| 0x03 | 1             | ERROR             | Stores errors, allows errors to be reset                                                    |
| 0x15 | 10            | SCHEDULE          | Responsible for managing Timers, the schedule, etc. Check here for level, bypass etc.       |
| 0x16 | 2             | VALVE             | ??? Bypass PreHeater and Extract                                                            |
| 0x17 | 2             | FAN               | Represents the two fans (supply, exhaust)                                                   |
| 0x18 | 1             | POWERSENSOR       | Counts the actual wattage of ventilation and accumulates to year and since factory reset    |
| 0x19 | 1             | PREHEATER         | Represents the optional preheater                                                           |
| 0x1A | 1             | HMI               | Represents the Display + Buttons                                                            |
| 0x1B | 1             | RFCOMMUNICATION   | Wireless-communication with attached devices                                                |
| 0x1C | 1             | FILTER            | Counts the days since last filter change                                                    |
| 0x1D | 1             | TEMPHUMCONTROL    | Controls the target temperature, if its cooling or heating period and some settings         |
| 0x1E | 1             | VENTILATIONCONFIG | Responsible for managing various configuration options of the ventilation                   |
| 0x20 | 1             | NODECONFIGURATION | Manages also some options                                                                   |
| 0x21 | 6             | TEMPERATURESENSOR | Represents the 6 temperature sensors in the ventilation                                     |
| 0x22 | 6             | HUMIDITYSENSOR    | Represents the 6 humidity sensors                                                           |
| 0x23 | 2             | PRESSURESENSOR    | Represents both pressure sensors                                                            |
| 0x24 | 1             | PERIPHERALS       | Stores the ID of the ComfoCool attached, can reset peripheral errors here                   |
| 0x25 | 4             | ANALOGINPUT       | Provides data and functionality for the analog inputs, also the scaling for the voltages    |
| 0x26 | 1             | COOKERHOOD        | "Dummy" unit, probably represents the ComfoHood if attached                                 |
| 0x27 | 1             | POSTHEATER        | Represents the optional post heater attached (temperature sens, config)                     |
| 0x28 | 1             | COMFOFOND         | "Dummy" unit, represents the optional comfofond                                             |

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

  Example: Request: `01 20 01 10 03`, Response: `34 32 31 30 00` (4210\0)
  This gets the maintainer password. Unit is `NODECONFIGURATION`, SubUnit is `01`, get the actual value, Property `03`.

- `0x02`: Get multiple properties

  This command allows to read multiple properties in one request.

  Syntax: `02 Unit SubUnit 01 Type Property1 Property2 ... PropertyN`

  The `Type` value needs to be OR'ed with the number of properties. So if you want to read the actual value of 5 properties, the `Type` value needs to be
  `0x10 | 0x05` = `0x15`.

  Example: Request: `02 01 01 01 15 03 04 06 05 14`, Response: `\02 BEA000000000000\00 \00\10\10\c0 \02 ComfoAirQ\00`
  This reads the following property values:
    - 0x03: ???
    - 0x04: Serial Number
    - 0x06: Firmware version
    - 0x05: ???
    - 0x14: Ventilation Unit Name

- `0x03`: Set a single property

  This commands sets one property to the given value. The value needs to be in the range as identified within 0x01, otherwise an error of 30 is returned. The
  step size, however, is not checked.

  Syntax: `03 Unit SubUnit Property Value`

  Example: `03 1D 01 04 00`
  Unit is `TEMPHUMCONTROL`, SubUnit `01`, Property: `04`, value `00`
  Sets the Property "Sensor ventilation: Temperature passive" to off

All other commands are >= `0x80` and dependent on the SubUnit. Please do not try to run command `0x80`, `0x82` on NODECONFIGURATION (`0x20`), they will probably
break your configuration, and even worse would be calling ANY >= `0x80` command on NODE (`0x01`). It can probably completely brick your ventilation. (It enters
factory mode or tries to perform an update.)

### Known properties for Node 0x01 (Ventilation Unit)

| Unit              | SubUnit | Property | Access | Format | Description                                                            |
|-------------------|---------|----------|--------|--------|------------------------------------------------------------------------|
| NODE              | 0x01    | 0x01     |        | UINT8  | ?? `01` = 1                                                            |
| NODE              | 0x01    | 0x02     |        | UINT8  | ?? `01` = 1                                                            |
| NODE              | 0x01    | 0x03     |        | UINT8  | ?? `02` = 2                                                            |
| NODE              | 0x01    | 0x04     | ro     | STRING | Serial number (BEA009999999999)                                        |
| NODE              | 0x01    | 0x05     |        | UINT8  | ?? `02` = 2                                                            |
| NODE              | 0x01    | 0x06     | ro     | UINT32 | Firmware version (See `version_decode()`)                              |
| NODE              | 0x01    | 0x07     |        | UINT32 | ?? `00541040` = 1074811904                                             |
| NODE              | 0x01    | 0x08     | ro     | STRING | Model number (ComfoAir Q450 B R RF ST Quality)                         |
| NODE              | 0x01    | 0x09     |        | UINT32 | ?? `04000000` = 4                                                      |
| NODE              | 0x01    | 0x0A     |        | UINT32 | ?? `0004f0c0` = 3236955136                                             |
| NODE              | 0x01    | 0x0B     | ro     | STRING | Article number (471502004)                                             |
| NODE              | 0x01    | 0x0C     |        | STRING | ?? NULL                                                                |
| NODE              | 0x01    | 0x0D     | ro     | STRING | Current Country (BE)                                                   |
| NODE              | 0x01    | 0x14     | ro     | STRING | Ventilation Unit Name (ComfoAirQ)                                      |
| TEMPHUMCONTROL    | 0x01    | 0x01     |        | UINT8  | ?? `01` = 1                                                            |
| TEMPHUMCONTROL    | 0x01    | 0x02     | rw     | INT16  | RMOT for heating period (180 -> 18°C)                                  |
| TEMPHUMCONTROL    | 0x01    | 0x03     | rw     | INT16  | RMOT for cooling period (200 -> 20°C)                                  |
| TEMPHUMCONTROL    | 0x01    | 0x04     | rw     | UINT8  | Passive temperature control (0=off, 1=autoonly, 2=on)                  |
| TEMPHUMCONTROL    | 0x01    | 0x05     | rw     | UINT8  | ?? `00` = 0                                                            |
| TEMPHUMCONTROL    | 0x01    | 0x06     | rw     | UINT8  | Humidity comfort control (o=off, 1=autoonly, 2=on)                     |
| TEMPHUMCONTROL    | 0x01    | 0x07     | rw     | UINT8  | Humidity protection (0=off, 1=autoonly, 2=on)                          |
| TEMPHUMCONTROL    | 0x01    | 0x08     | rw     | UINT8  | ?? `00` = 0                                                            |
| TEMPHUMCONTROL    | 0x01    | 0x0A     | rw     | INT16  | Target temperature for profile: Heating (230 -> 23°C)                  |
| TEMPHUMCONTROL    | 0x01    | 0x0B     | rw     | INT16  | Target temperature for profile: Normal (210 -> 21°C)                   |
| TEMPHUMCONTROL    | 0x01    | 0x0C     | rw     | INT16  | Target temperature for profile: Cooling (190 -> 19°C)                  |
| TEMPHUMCONTROL    | 0x01    | 0x0D     |        | UINT8  | ?? `00` = 0                                                            |
| VENTILATIONCONFIG | 0x01    | 0x01     |        | UINT8  | ?? `01` = 1                                                            |
| VENTILATIONCONFIG | 0x01    | 0x02     |        | UINT8  | ?? `0f` = 15                                                           |
| VENTILATIONCONFIG | 0x01    | 0x03     | rw     | INT16  | Ventilation speed in "Away" Level (75)                                 |
| VENTILATIONCONFIG | 0x01    | 0x04     | rw     | INT16  | Ventilation speed in "Low" Level (110)                                 |
| VENTILATIONCONFIG | 0x01    | 0x05     | rw     | INT16  | Ventilation speed in "Medium" Level (180)                              |
| VENTILATIONCONFIG | 0x01    | 0x06     | rw     | INT16  | Ventilation speed in "High" Level (370)                                |
| VENTILATIONCONFIG | 0x01    | 0x07     |        | UINT8  | Height above sea level (0=0-500, 1=500-1000, 2=1000-1500, 3=1500-2000) |
| VENTILATIONCONFIG | 0x01    | 0x08     |        | INT16  | ?? `8b01` = 395,420                                                    |
| VENTILATIONCONFIG | 0x01    | 0x09     |        | UINT8  | Ventilation control mode (0=flow control, 1=constant flow)             |
| VENTILATIONCONFIG | 0x01    | 0x0a     |        | INT16  | ?? `ecff` = -20                                                        |
| VENTILATIONCONFIG | 0x01    | 0x0b     |        | INT16  | Bathroom switch, activation delay (`300` = 300 sec)                    |
| VENTILATIONCONFIG | 0x01    | 0x0c     |        | UINT8  | Bathroom switch, deactivation delay (`30` = 30 min)                    |
| VENTILATIONCONFIG | 0x01    | 0x0d     |        | UINT8  | Bathroom switch, mode (0=fixed, 1=mirrored)                            |
| VENTILATIONCONFIG | 0x01    | 0x0e     |        | UINT8  | ?? `03` = 3                                                            |
| VENTILATIONCONFIG | 0x01    | 0x0f     |        | UINT8  | ?? `00` = 0                                                            |
| VENTILATIONCONFIG | 0x01    | 0x11     |        | INT16  | ?? `c800` = 200                                                        |
| VENTILATIONCONFIG | 0x01    | 0x12     |        | INT16  | Unbalance (`9dff` = -99 -> -9.9)                                       |
| VENTILATIONCONFIG | 0x01    | 0x13     |        | INT16  | ?? `0000` = 0                                                          |
| VENTILATIONCONFIG | 0x01    | 0x14     |        | INT16  | ?? `0000` = 0                                                          |
| VENTILATIONCONFIG | 0x01    | 0x15     |        | INT16  | ?? `980d` = 3480                                                       |
| VENTILATIONCONFIG | 0x01    | 0x16     |        | INT16  | ?? `660c` = 3174                                                       |
| VENTILATIONCONFIG | 0x01    | 0x17     |        | INT16  | ?? `0000` = 0                                                          |
| VENTILATIONCONFIG | 0x01    | 0x18     |        | INT16  | ?? `0000` = 0                                                          |
| VENTILATIONCONFIG | 0x01    | 0x19     |        | INT16  | ?? `8107` = 1921                                                       |
| VENTILATIONCONFIG | 0x01    | 0x1a     |        | INT16  | ?? `a106` = 1697                                                       |
| VENTILATIONCONFIG | 0x01    | 0x1b     |        | INT16  | ?? `0f05` = 1295                                                       |
| VENTILATIONCONFIG | 0x01    | 0x1c     |        | INT16  | ?? `0c05` = 1292                                                       |
| VENTILATIONCONFIG | 0x01    | 0x1d     |        | INT16  | ?? `5304` = 1107                                                       |
| VENTILATIONCONFIG | 0x01    | 0x1e     |        | INT16  | ?? `1304` = 1043                                                       |
| NODECONFIGURATION | 0x01    | 0x01     |        | UINT8  | ?? `01` = 1                                                            |
| NODECONFIGURATION | 0x01    | 0x03     |        | STRING | Maintainer password (NL=4210, BE=2468, DE=4210)                        |
| NODECONFIGURATION | 0x01    | 0x04     |        | UINT8  | Orientation (0=left, 1=right)                                          |
| NODECONFIGURATION | 0x01    | 0x05     |        | UINT8  | ?? `01` = 1                                                            |
| NODECONFIGURATION | 0x01    | 0x06     |        | UINT8  | ?? `00` = 0                                                            |
| NODECONFIGURATION | 0x01    | 0x07     |        | UINT8  | ?? `00` = 0                                                            |
| NODECONFIGURATION | 0x01    | 0x08     |        | UINT8  | ?? `01` = 1                                                            |
| NODECONFIGURATION | 0x01    | 0x0A     |        | UINT8  | ?? `00` = 0                                                            |
| NODECONFIGURATION | 0x01    | 0x0B     |        | UINT8  | ?? `02` = 2                                                            |
| NODECONFIGURATION | 0x01    | 0x0C     |        | UINT8  | ?? `01` = 1                                                            |

### Known properties for Node 0x30 (ComfoConnect LAN C)

| Unit              | SubUnit | Property | Access | Format | Description                                                            |
|-------------------|---------|----------|--------|--------|------------------------------------------------------------------------|
| NODE              | 0x01    | 0x01     |        | UINT8  | ?? `ff` = 255                                                          |
| NODE              | 0x01    | 0x02     |        | UINT8  | ?? `05` = 5                                                            |
| NODE              | 0x01    | 0x03     |        | UINT8  | ?? `00` = 0                                                            |
| NODE              | 0x01    | 0x04     | ro     | STRING | Serial number (DEM0999999999)                                          |
| NODE              | 0x01    | 0x05     |        | UINT8  | ?? `01` = 1                                                            |
| NODE              | 0x01    | 0x06     | ro     | UINT32 | Firmware version (See `version_decode()`)                              |
| NODE              | 0x01    | 0x07     |        | UINT32 | ?? `008c10c0` = 3222309888                                             |
| NODE              | 0x01    | 0x14     | ro     | STRING | Unit Name (ComfoConnect LAN C)                                         |

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

| SubUnit | Property | Description                                       |
|:--------|----------|---------------------------------------------------|
| 0x01    | 0x01     | Preset (`00`=away/`01`=low/`02`=medium/`03`=high) |
| 0x01    | 0x02     | PRESETRF                                          |
| 0x01    | 0x03     | PRESETANALOG                                      |
| 0x01    | 0x04     | PRESETRFANALOG                                    |
| 0x01    | 0x05     | MANUALMODE                                        |
| 0x01    | 0x06     | BOOST                                             |
| 0x01    | 0x07     | BOOSTRF                                           |
| 0x01    | 0x08     | BOOSTSWITCH                                       |
| 0x01    | 0x0b     | AWAY                                              |
| 0x02    | 0x01     | Bypass control (auto/on/off)                      |
| 0x03    | 0x01     | Temperature profile (warm/normal/cool)            |
| 0x05    | 0x01     | Comfocool control                                 |
| 0x06    | 0x01     | Supply fan control                                |
| 0x07    | 0x01     | Exhaust fan control                               |
| 0x08    | 0x01     | Ventilation mode (auto/manual)                    |

## ERROR Unit commands

- `0x80`: GETACTIVEERRORS
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
|          | # Firmware 1.4.0+                                                                                                                                 |
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
|          |                                                                                                                                                   |
|          | # Firmware 1.4.0                                                                                                                                  |
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


## Time Management (Alternative Method)

In addition to the PDO-based time synchronization (see PROTOCOL-PDO.md), time can be managed through direct CAN bus commands without using the RMI protocol.

### Direct CAN Bus Time Commands

These commands operate outside the RMI request/response framework and communicate directly with the device's internal clock.

#### Read Time (RTR Method)

Unlike RMI requests, time can be requested using a Remote Transmission Request:

```
CAN ID: 0x10080028 (Extended)
Type:   RTR (Remote Transmission Request)
DLC:    0

Response:
CAN ID: 0x10040001 (Extended)
DLC:    4
Data:   [B0] [B1] [B2] [B3]  (little-endian uint32)
```

The response contains seconds since 2000-01-01 00:00:00 (device epoch).

#### Write Time

Time is set by sending a data frame directly to the device:

```
CAN ID: 0x10040001 (Extended)
DLC:    4
Data:   [B0] [B1] [B2] [B3]  (little-endian uint32)
```

Where the data represents seconds since 2000-01-01 00:00:00.

### Time Format

| Field | Type | Description |
|-------|------|-------------|
| Seconds | uint32 | Seconds since 2000-01-01 00:00:00 |

**Conversion:**
```
Device Seconds = Unix Timestamp - 946684800
Unix Timestamp = Device Seconds + 946684800
```

### Example Usage

**Setting time to 2025-10-27 15:30:00:**

```
Step 1: Calculate Unix timestamp
2025-10-27 15:30:00 = 1730044200 (Unix)

Step 2: Convert to device seconds
1730044200 - 946684800 = 783359400

Step 3: Convert to hex
783359400 = 0x2EAEFAB8

Step 4: Send as little-endian
CAN ID: 0x10040001
Data: [B8 FA AE 2E]
```

---
