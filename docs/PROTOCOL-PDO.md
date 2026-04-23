# PDO sensors

## PDO data types

Numbers are stored in little endian format.

| type | description | remark                    |
|------|-------------|---------------------------|
| 0    | CN_BOOL     | `00` (false), `01` (true) |
| 1    | CN_UINT8    | `00` (0) until `ff` (255) |
| 2    | CN_UINT16   | `3412` = 1234             |
| 3    | CN_UINT32   | `7856 3412` = 12345678    |
| 5    | CN_INT8     |                           |
| 6    | CN_INT16    | `3412` = 1234             |
| 8    | CN_INT64    |                           |
| 9    | CN_STRING   |                           |
| 10   | CN_TIME     |                           |
| 11   | CN_VERSION  |                           |

# Overview of known sensors

| pdid | type      | description                                      | examples                                                                                                         |
|------|-----------|--------------------------------------------------|------------------------------------------------------------------------------------------------------------------|
| 16   | CN_UINT8  | Device state                                     | 0=init, 1=normal, 2=filterwizard, 3=commissioning, 4=supplierfactory, 5=zehnderfactory, 6=standby, 7=away, 8=DFC |
| 17   | CN_UINT8  | ?? ROOM_T10                                      |                                                                                                                  |
| 18   | CN_UINT8  | Changing filters                                 | 1=active, 2=changing filter                                                                                      |
| 33   | CN_UINT8  | ?? Preset                                        | 0, 1                                                                                                             |
| 35   | CN_UINT8  | ?? Temperature Profile                           | 1                                                                                                                |
| 36   | CN_UINT8  | ?? STANDBY                                       |                                                                                                                  |
| 37   | CN_UINT8  |                                                  | 0                                                                                                                |
| 40   | CN_UINT8  | ?? MANUALMODE                                    |                                                                                                                  |
| 42   | CN_UINT8  |                                                  | 0                                                                                                                |
| 49   | CN_UINT8  | Operating mode                                   | -1=auto, 1=limited manual, 5=unlimited manual, 6=boost                                                           |
| 50   | CN_UINT8  | ?? Bypass                                        |                                                                                                                  |
| 51   | CN_UINT8  | ?? Temperature Profile                           |                                                                                                                  |
| 52   | CN_UINT8  | ?? STANDBY                                       |                                                                                                                  |
| 53   | CN_UINT8  | ?? COMFOCOOLOFF                                  | -1, 0, 1                                                                                                         |
| 54   | CN_UINT8  | Supply Fan Mode                                  | -1=balanced, 1=supply only                                                                                       |
| 55   | CN_UINT8  | Exhaust Fan Mode                                 | -1=balanced, 1=exhaust only                                                                                      |
| 56   | CN_UINT8  | Manual Mode                                      | -1=auto, 1=unlimited manual                                                                                      |
| 57   | CN_UINT8  |                                                  | -1, 0                                                                                                            |
| 58   | CN_UINT8  |                                                  | -1, 0                                                                                                            |
| 65   | CN_UINT8  | Fans: Fan speed setting                          | 0=away, 1=low, 2=medium, 3=high                                                                                  |
| 66   | CN_UINT8  | Bypass activation mode                           | 0=auto, 1=full, 2=none                                                                                           |
| 67   | CN_UINT8  | Temperature Profile                              | 0=normal, 1=cold, 2=warm                                                                                         |
| 68   | CN_UINT8  | ?? STANDBY                                       | 0                                                                                                                |
| 69   |           | ?? COMFOCOOLOFF                                  | 0=auto, 1=off                                                                                                    |
| 70   | CN_UINT8  | Supply Fan Mode                                  | 0=balanced, 1=supply only                                                                                        |
| 71   | CN_UINT8  | Exhaust Fan Mode                                 | 0=balanced, 1=exhaust only                                                                                       |
| 72   | CN_UINT8  | ?? MANUALMODE                                    |                                                                                                                  |
| 73   | CN_UINT8  |                                                  | 0                                                                                                                |
| 74   | CN_UINT8  |                                                  | 0                                                                                                                |
| 81   | CN_UINT32 | Fan Speed Next Change                            | -1=no change, else countdown in seconds                                                                          |
| 82   | CN_UINT32 | Bypass Next Change                               | -1=no change, else countdown in seconds                                                                          |
| 85   | CN_UINT32 | ComfoCool Next Change                            | -1=no change, else countdown in seconds                                                                          |
| 86   | CN_UINT32 | Supply Fan Next Change                           | -1=no change, else countdown in seconds                                                                          |
| 87   | CN_UINT32 | Exhaust Fan Next Change                          | -1=no change, else countdown in seconds                                                                          |
| 88   | CN_UINT32 | ?? MANUALMODE                                    |                                                                                                                  |
| 89   | CN_UINT32 |                                                  | -1, 0                                                                                                            |
| 90   | CN_UINT32 |                                                  | -1, 0                                                                                                            |
| 96   | CN_BOOL   |                                                  |                                                                                                                  |
| 115  | CN_BOOL   | ?? EXHAUST_F12                                   |                                                                                                                  |
| 116  | CN_BOOL   | ?? SUPPLY_F22                                    |                                                                                                                  |
| 117  | CN_UINT8  | Fans: Exhaust fan duty                           | value in % (28%)                                                                                                 |
| 118  | CN_UINT8  | Fans: Supply fan duty                            | value in % (29%)                                                                                                 |
| 119  | CN_UINT16 | Fans: Exhaust fan flow                           | value in m³/h (110 m³/h)                                                                                         |
| 120  | CN_UINT16 | Fans: Supply fan flow                            | value in m³/h (105 m³/h                                                                                          |
| 121  | CN_UINT16 | Fans: Exhaust fan speed                          | value in rpm (1069 rpm)                                                                                          |
| 122  | CN_UINT16 | Fans: Supply fan speed                           | value in rpm (1113 rpm)                                                                                          |
| 128  | CN_UINT16 | Power Consumption: Current Ventilation           | value in Watt (15 W)                                                                                             |
| 129  | CN_UINT16 | Power Consumption: Total year-to-date            | value in kWh (23 kWh)                                                                                            |
| 130  | CN_UINT16 | Power Consumption: Total from start              | value in kWh (23 kWh)                                                                                            |
| 144  | CN_UINT16 | Preheater Power Consumption: Total year-to-date  | value in kWh (23 kWh)                                                                                            |
| 145  | CN_UINT16 | Preheater Power Consumption: Total from start    | value in kWh (23 kWh)                                                                                            |
| 146  | CN_UINT16 | Preheater Power Consumption: Current Ventilation | value in Watt (15 W)                                                                                             |
| 176  | CN_UINT8  | RF Pairing Mode                                  | 0=not running, 1=running, 2=done, 3=failed, 4=aborted                                                            |
| 192  | CN_UINT16 | Days left before filters must be replaced        | value in days (130 days)                                                                                         |
| 208  | CN_UINT8  | Device Temperature Unit                          | 0=celsius, 1=farenheit                                                                                           |
| 209  | CN_INT16  | Running Mean Outdoor Temperature (RMOT)          | value in °C (117 -> 11.7 °C)                                                                                     |
| 210  | CN_BOOL   | Heating Season is active                         | 0=inactive, 1=active                                                                                             |
| 211  | CN_BOOL   | Cooling Season is active                         | 0=inactive, 1=active                                                                                             |
| 212  | CN_UINT8  | Temperature profile target                       | value in °C (238 -> 23.8 °C)                                                                                     |
| 213  | CN_UINT16 | Avoided Heating: Avoided actual                  | value in Watt (441 -> 4.41 W)                                                                                    |
| 214  | CN_UINT16 | Avoided Heating: Avoided year-to-date            | value in kWh (477 kWh)                                                                                           |
| 215  | CN_UINT16 | Avoided Heating: Avoided total                   | value in kWh (477 kWh)                                                                                           |
| 216  | CN_UINT16 | Avoided Cooling: Avoided actual                  | value in Watt (441 -> 4.41 W)                                                                                    |
| 217  | CN_UINT16 | Avoided Cooling: Avoided year-to-date            | value in kWh (477 kWh)                                                                                           |
| 218  | CN_UINT16 | Avoided Cooling: Avoided total                   | value in kWh (477 kWh)                                                                                           |
| 219  | CN_UINT16 |                                                  | 0                                                                                                                |
| 220  | CN_INT16  | ?? Outdoor Air Temperature (Preheated)           | value in °C (75 -> 7.5 °C)                                                                                       |
| 221  | CN_INT16  | ?? Temperature: Supply Air (PostHeated)          | value in °C (170 -> 17.0 °C)                                                                                     |
| 224  | CN_UINT8  | Device Airflow Unit                              | 1=kg/h, 2=l/s, 3=m³/h                                                                                            |
| 225  | CN_UINT8  | Sensor based ventilation mode                    | 0=disabled, 1=active, 2=overruling                                                                               |
| 226  | CN_UINT16 | Fan Speed (modulated)                            | 0, 100, 200, 300 (0-300 when modulating and PDO 225=2)                                                           |
| 227  | CN_UINT8  | Bypass state                                     | value in % (100% = fully open)                                                                                   |
| 228  | CN_UINT8  | ?? FrostProtectionUnbalance                      | 0                                                                                                                |
| 229  | CN_BOOL   |                                                  | 1                                                                                                                |
| 230  | CN_INT64  | Ventilation Constraints Bitset                   | See calculate_airflow_constraints()                                                                              |
| 256  | CN_UINT8  |                                                  | 1=basic, 2=advanced, 3=installer                                                                                 |
| 257  | CN_UINT8  |                                                  |                                                                                                                  |
| 274  | CN_INT16  | Temperature: Extract Air                         | value in °C (171 -> 17.1 °C)                                                                                     |
| 275  | CN_INT16  | Temperature: Exhaust Air                         | value in °C (86 -> 8.6 °C)                                                                                       |
| 276  | CN_INT16  | Temperature: Outdoor Air                         | value in °C (60 -> 6.0 °C)                                                                                       |
| 277  | CN_INT16  | ?? Temperature: Outdoor Air (Preheated?)         | value in °C (60 -> 6.0 °C)                                                                                       |
| 278  | CN_INT16  | ?? Temperature: Supply Air (Preheated?)          | value in °C (184 -> 18.4 °C)                                                                                     |
| 290  | CN_UINT8  | Humidity: Extract Air                            | value in % (49%)                                                                                                 |
| 291  | CN_UINT8  | Humidity: Exhaust Air                            | value in % (87%)                                                                                                 |
| 292  | CN_UINT8  | Humidity: Outdoor Air                            | value in % (67%)                                                                                                 |
| 293  | CN_UINT8  | Humidity: Preheated Outdoor Air                  | value in % (67%)                                                                                                 |
| 294  | CN_UINT8  | Humidity: Supply Air                             | value in % (35%)                                                                                                 |
| 321  | CN_UINT16 |                                                  | 3                                                                                                                |
| 325  | CN_UINT16 | ?? COMFOCOOLOFF                                  | 0, 1, 3                                                                                                          |
| 328  | CN_UINT16 | ?? MANUALMODE                                    |                                                                                                                  |
| 330  | CN_UINT16 |                                                  | 0, 1                                                                                                             |
| 337  | CN_UINT32 | ?? PRESET                                        | 0, 2, 32, 34                                                                                                     |
| 338  | CN_UINT32 | Bypass Override                                  | 0=auto, 2=overriden                                                                                              |
| 341  | CN_UINT32 | ?? COMFOCOOLOFF                                  | 00000000, 02000000                                                                                               |
| 342  | CN_UINT32 | Supply Fan Mode                                  | 0 = balanced, 2 = supply only                                                                                    |
| 343  | CN_UINT32 | Exhaust Fan Mode                                 | 0 = balanced, 2 = exhaust only                                                                                   |
| 344  | CN_UINT32 | ?? MANUAL MODE                                   |                                                                                                                  |
| 345  | CN_UINT32 |                                                  | 0                                                                                                                |
| 346  | CN_UINT32 |                                                  | 0                                                                                                                |
| 369  | CN_UINT8  | Analog Input 0-10V 1                             | 0                                                                                                                |
| 370  | CN_UINT8  | Analog Input 0-10V 2                             | 0                                                                                                                |
| 371  | CN_UINT8  | Analog Input 0-10V 3                             | 0                                                                                                                |
| 372  | CN_UINT8  | Analog Input 0-10V 4                             | 0                                                                                                                |
| 384  | CN_INT16  |                                                  | 0.0                                                                                                              |
| 386  | CN_BOOL   |                                                  | 0                                                                                                                |
| 400  | CN_INT16  |                                                  | 0.0                                                                                                              |
| 401  | CN_UINT8  |                                                  | 0                                                                                                                |
| 402  | CN_BOOL   | ?? PostHeaterPresent                             | 0                                                                                                                |
| 416  | CN_INT16  | ComfoFond Outdoor Air Temperature                | -40.0                                                                                                            |
| 417  | CN_INT16  | ComfoFond Ground Temperature                     | 10.0                                                                                                             |
| 418  | CN_UINT8  | ComfoFond GHE State Percentage                   | 0                                                                                                                |
| 419  | CN_BOOL   | ComfoFond GHE Present                            | 0=absent, 1=present                                                                                              |
| 513  | CN_UINT16 |                                                  |                                                                                                                  |
| 514  | CN_UINT16 |                                                  |                                                                                                                  |
| 515  | CN_UINT16 |                                                  |                                                                                                                  |
| 516  | CN_UINT16 |                                                  |                                                                                                                  |
| 517  | CN_UINT8  |                                                  |                                                                                                                  |
| 518  | CN_UINT8  |                                                  |                                                                                                                  |
| 519  | CN_UINT8  |                                                  |                                                                                                                  |
| 520  | CN_UINT8  |                                                  |                                                                                                                  |
| 521  | CN_INT16  |                                                  |                                                                                                                  |
| 522  | CN_INT16  |                                                  |                                                                                                                  |
| 523  | CN_INT16  |                                                  |                                                                                                                  |
| 524  | CN_UINT8  |                                                  |                                                                                                                  |
| 784  | CN_UINT8  | ComfoCool State                                  | 0=off, 1=on (0)                                                                                                  |
| 785  | CN_BOOL   | ?? ComfoCoolCompressor State                     | 0                                                                                                                |
| 801  | CN_INT16  | ?? T10ROOMTEMPERATURE                            | 0.0                                                                                                              |
| 802  | CN_INT16  | ComfoCool Condensor Temperature                  | 0.0                                                                                                              |
| 803  | CN_INT16  | ?? T23SUPPLYAIRTEMPERATURE                       | 0.0                                                                                                              |
| 1024 | CN_UINT16 |                                                  |                                                                                                                  |
| 1025 | CN_UINT16 |                                                  |                                                                                                                  |
| 1026 | CN_UINT16 |                                                  |                                                                                                                  |
| 1027 | CN_UINT16 |                                                  |                                                                                                                  |
| 1028 | CN_UINT16 |                                                  |                                                                                                                  |
| 1029 | CN_UINT16 |                                                  |                                                                                                                  |
| 1030 | CN_UINT16 |                                                  |                                                                                                                  |
| 1031 | CN_UINT16 |                                                  |                                                                                                                  |
| 1056 | CN_INT16  |                                                  |                                                                                                                  |
| 1124 | CN_INT16  |                                                  |                                                                                                                  |
| 1125 | CN_INT16  |                                                  |                                                                                                                  |
| 1126 | CN_INT16  |                                                  |                                                                                                                  |
| 1127 | CN_INT16  |                                                  |                                                                                                                  |
| 1281 | CN_UINT16 |                                                  |                                                                                                                  |
| 1282 | CN_UINT16 |                                                  |                                                                                                                  |
| 1283 | CN_UINT16 |                                                  |                                                                                                                  |
| 1284 | CN_UINT16 |                                                  |                                                                                                                  |
| 1285 | CN_UINT16 |                                                  |                                                                                                                  |
| 1286 | CN_UINT16 |                                                  |                                                                                                                  |
| 1287 | CN_UINT16 |                                                  |                                                                                                                  |
| 1288 | CN_UINT16 |                                                  |                                                                                                                  |
| 1297 | CN_BOOL   |                                                  |                                                                                                                  |
| 1298 | CN_BOOL   |                                                  |                                                                                                                  |
| 1299 | CN_BOOL   |                                                  |                                                                                                                  |
| 1300 | CN_BOOL   |                                                  |                                                                                                                  |
| 1301 | CN_BOOL   |                                                  |                                                                                                                  |
| 1302 | CN_BOOL   |                                                  |                                                                                                                  |
| 1303 | CN_BOOL   |                                                  |                                                                                                                  |
| 1304 | CN_BOOL   |                                                  |                                                                                                                  |


## Device Time (PDO ID: 0x0A)

The device maintains an internal real-time clock that can be synchronized via CAN bus.

### Time Representation

Time is stored as a 32-bit unsigned integer representing seconds elapsed since the device epoch: **2000-01-01 00:00:00**.

**Conversion formula:**
```
Device Seconds = Unix Timestamp - 946684800
```

Where `946684800` is the number of seconds between the Unix epoch (1970-01-01) and the device epoch (2000-01-01).

### Reading Device Time

**Request:**
- CAN ID: `0x10080028` (Extended)
- Type: Remote Transmission Request (RTR)
- DLC: 0

**Response:**
- CAN ID: `0x10040001` (Extended)
- DLC: 4
- Data: Little-endian uint32 (seconds since 2000-01-01)

**Example:**
```
Request:  CAN ID 0x10080028, RTR, DLC 0
Response: CAN ID 0x10040001, Data [14 EE 90 30]
          = 0x3090EE14 = 814804500 seconds
          = 2025-10-26 14:35:00
```

### Setting Device Time

**Command:**
- CAN ID: `0x10040001` (Extended)
- DLC: 4
- Data: Little-endian uint32 (seconds since 2000-01-01)

**Note:** The device displays time without timezone conversion. Send local time directly for the device to display local time.

**Example:**
```
To set device to 2025-10-27 15:30:00:
Unix timestamp: 1730044200
Device seconds: 1730044200 - 946684800 = 783359400 = 0x2EAEFAB8

CAN ID: 0x10040001
Data: [B8 FA AE 2E]  (little-endian)
```

### Notes

- Multiple request attempts recommended for reliability (2-3 times with 100ms spacing)
- Response timeout: 5 seconds
- No explicit acknowledgment for set command; verify by reading time back
- First request after boot may timeout
