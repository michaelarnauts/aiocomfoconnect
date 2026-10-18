# PDO sensors

## PDO data types

Numbers are stored in little endian format.

Unsigned PDO notifications are decoded using the type requested for the subscription.
An all-ones value is `255` for `CN_UINT8` and `4294967295` for `CN_UINT32`.
These values represent the mode or no-change sentinels shown below; older versions
decoded them as `-1`. Signed PDO types still preserve negative values.

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

Most pdids from 33 to 90 and from 321 to 346 belong to a schedule; see [Schedule PDOs](#schedule-pdos).
A † marks a meaning or a value that is derived from that pattern and the official app, but has not been seen on a
unit yet.

| pdid | type      | description                                      | examples                                                                                                         |
|------|-----------|--------------------------------------------------|------------------------------------------------------------------------------------------------------------------|
| 16   | CN_UINT8  | Device state                                     | 0=init, 1=normal, 2=filterwizard, 3=commissioning, 4=supplierfactory, 5=zehnderfactory, 6=standby, 7=away, 8=DFC |
| 17   | CN_UINT8  | ?? ROOM_T10                                      |                                                                                                                  |
| 18   | CN_UINT8  | Changing filters                                 | 1=active, 2=changing filter                                                                                      |
| 33   | CN_UINT8  | Preset: active schedule entry †                  | idle: 1                                                                                                          |
| 34   | CN_UINT8  | Bypass: active schedule entry †                  | idle: 0                                                                                                          |
| 35   | CN_UINT8  | Temperature profile: active schedule entry †     | idle: 0                                                                                                          |
| 36   | CN_UINT8  | Standby: active schedule entry †                 | idle: 0                                                                                                          |
| 37   | CN_UINT8  | ComfoCool off: active schedule entry †           | idle: 0                                                                                                          |
| 38   | CN_UINT8  | Exhaust fan off: active schedule entry †         | idle: 0                                                                                                          |
| 39   | CN_UINT8  | Supply fan off: active schedule entry †          | idle: 0                                                                                                          |
| 40   | CN_UINT8  | Manual mode: active schedule entry †             | idle: 0                                                                                                          |
| 41   | CN_UINT8  | Hood: active schedule entry †                    | idle: 0                                                                                                          |
| 42   | CN_UINT8  | Postheater: active schedule entry †              | idle: 0                                                                                                          |
| 49   | CN_UINT8  | Operating mode (preset: active timer)            | 255=auto, 1=limited manual, 5=unlimited manual, 6=boost, 11=away (the `SCHEDULE_PRESET` timer ids)               |
| 50   | CN_UINT8  | Bypass: active timer                             | 255=none, 1=timer †                                                                                              |
| 51   | CN_UINT8  | Temperature profile: active timer                | 255=none, 1=timer                                                                                                |
| 52   | CN_UINT8  | Standby: active timer                            | 255=none, 1=timer †                                                                                              |
| 53   | CN_UINT8  | ComfoCool off: active timer                      | 255=none, 1=timer                                                                                                |
| 54   | CN_UINT8  | Supply Fan Mode (exhaust fan off: active timer)  | 255=balanced, 1=supply only                                                                                      |
| 55   | CN_UINT8  | Exhaust Fan Mode (supply fan off: active timer)  | 255=balanced, 1=exhaust only                                                                                     |
| 56   | CN_UINT8  | Manual Mode (manual mode: active timer)          | 255=auto, 1=unlimited manual                                                                                     |
| 57   | CN_UINT8  | Hood: active timer                               | 255=none, 1=timer †, 2=switch timer †                                                                            |
| 58   | CN_UINT8  | Postheater: active timer                         | 255=none, 1=timer †                                                                                              |
| 65   | CN_UINT8  | Fans: Fan speed setting (preset: value)          | 0=away, 1=low, 2=medium, 3=high                                                                                  |
| 66   | CN_UINT8  | Bypass activation mode (bypass: value)           | 0=auto, 1=full, 2=none                                                                                           |
| 67   | CN_UINT8  | Temperature Profile (temperature profile: value) | 0=normal, 1=cold, 2=warm                                                                                         |
| 68   | CN_UINT8  | Standby: value                                   | 0=off, 1=on †                                                                                                    |
| 69   | CN_UINT8  | ComfoCool off: value                             | 0=auto, 1=off                                                                                                    |
| 70   | CN_UINT8  | Supply Fan Mode (exhaust fan off: value)         | 0=balanced, 1=supply only                                                                                        |
| 71   | CN_UINT8  | Exhaust Fan Mode (supply fan off: value)         | 0=balanced, 1=exhaust only                                                                                       |
| 72   | CN_UINT8  | Manual mode: value                               | 0=off, 1=on †                                                                                                    |
| 73   | CN_UINT8  | Hood: value                                      | 0=off, 1=on †                                                                                                    |
| 74   | CN_UINT8  | Postheater: value                                | 0=off, 1=heat †, 2=comfort †                                                                                     |
| 81   | CN_UINT32 | Fan Speed Next Change (preset: remaining)        | 4294967295=no timer or no end, else countdown in seconds (e.g. of a boost timer)                                 |
| 82   | CN_UINT32 | Bypass Next Change (bypass: remaining)           | 4294967295=no change, else countdown in seconds                                                                  |
| 83   | CN_UINT32 | Temperature profile: remaining                   | 4294967295=no timer or no end (seen with a timer without end), else countdown in seconds †                       |
| 84   | CN_UINT32 | Standby: remaining                               | 4294967295=no timer or no end, else countdown in seconds †                                                       |
| 85   | CN_UINT32 | ComfoCool off: remaining                         | 4294967295=no timer or no end, else countdown in seconds †                                                       |
| 86   | CN_UINT32 | Supply Fan Next Change (exhaust fan off: remaining) | 4294967295=no change, else countdown in seconds                                                                  |
| 87   | CN_UINT32 | Exhaust Fan Next Change (supply fan off: remaining) | 4294967295=no change, else countdown in seconds                                                                  |
| 88   | CN_UINT32 | Manual mode: remaining                           | 4294967295=no timer or no end, else countdown in seconds †                                                       |
| 89   | CN_UINT32 | Hood: remaining                                  | 4294967295=no timer or no end, else countdown in seconds †                                                       |
| 90   | CN_UINT32 | Postheater: remaining                            | 4294967295=no timer or no end, else countdown in seconds †                                                       |
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
| 213  | CN_UINT16 | Avoided Heating: Avoided actual                  | value in Watt                                                                                                    |
| 214  | CN_UINT16 | Avoided Heating: Avoided year-to-date            | value in kWh (477 kWh)                                                                                           |
| 215  | CN_UINT16 | Avoided Heating: Avoided total                   | value in kWh (477 kWh)                                                                                           |
| 216  | CN_UINT16 | Avoided Cooling: Avoided actual                  | value in Watt                                                                                                    |
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
| 278  | CN_INT16  | Temperature: before the Postheater               | value in °C (184 -> 18.4 °C), the temperature after the postheater is 221                                        |
| 290  | CN_UINT8  | Humidity: Extract Air                            | value in % (49%)                                                                                                 |
| 291  | CN_UINT8  | Humidity: Exhaust Air                            | value in % (87%)                                                                                                 |
| 292  | CN_UINT8  | Humidity: Outdoor Air                            | value in % (67%)                                                                                                 |
| 293  | CN_UINT8  | Humidity: Preheated Outdoor Air                  | value in % (67%)                                                                                                 |
| 294  | CN_UINT8  | Humidity: Supply Air                             | value in % (35%)                                                                                                 |
| 321  | CN_UINT16 | Preset: enabled schedule entries (bit set) †     | idle: 3 (bits 0 and 1)                                                                                           |
| 322  | CN_UINT16 | Bypass: enabled schedule entries (bit set) †     | idle: 1 (bit 0)                                                                                                  |
| 323  | CN_UINT16 | Temperature profile: enabled schedule entries (bit set) † | idle: 1 (bit 0)                                                                                                  |
| 324  | CN_UINT16 | Standby: enabled schedule entries (bit set) †    | idle: 1 (bit 0)                                                                                                  |
| 325  | CN_UINT16 | ComfoCool off: enabled schedule entries (bit set) † | idle: 1 (bit 0); 0 and 3 also seen                                                                               |
| 326  | CN_UINT16 | Exhaust fan off: enabled schedule entries (bit set) † | idle: 1 (bit 0)                                                                                                  |
| 327  | CN_UINT16 | Supply fan off: enabled schedule entries (bit set) † | idle: 1 (bit 0)                                                                                                  |
| 328  | CN_UINT16 | Manual mode: enabled schedule entries (bit set) † | idle: 1 (bit 0)                                                                                                  |
| 329  | CN_UINT16 | Hood: enabled schedule entries (bit set) †       | idle: 1 (bit 0)                                                                                                  |
| 330  | CN_UINT16 | Postheater: enabled schedule entries (bit set) † | idle: 1 (bit 0); 0 also seen                                                                                     |
| 337  | CN_UINT32 | Preset: running timers (bit set)                 | 0=none, 2=timer 1, 32=timer 5, 34=timers 1 and 5, 64=timer 6 (boost), 2048=timer 11 (away) †                     |
| 338  | CN_UINT32 | Bypass Override (bypass: running timers)         | 0=auto, 2=overriden (timer 1)                                                                                    |
| 339  | CN_UINT32 | Temperature profile: running timers (bit set)    | 0=none, 2=timer 1                                                                                                |
| 340  | CN_UINT32 | Standby: running timers (bit set)                | 0=none, 2=timer 1 †                                                                                              |
| 341  | CN_UINT32 | ComfoCool off: running timers (bit set)          | 0=none, 2=timer 1                                                                                                |
| 342  | CN_UINT32 | Supply Fan Mode (exhaust fan off: running timers) | 0 = balanced, 2 = supply only (timer 1)                                                                          |
| 343  | CN_UINT32 | Exhaust Fan Mode (supply fan off: running timers) | 0 = balanced, 2 = exhaust only (timer 1)                                                                         |
| 344  | CN_UINT32 | Manual mode: running timers (bit set)            | 0=none, 2=timer 1 †                                                                                              |
| 345  | CN_UINT32 | Hood: running timers (bit set)                   | 0=none, 2=timer 1 †, 4=timer 2 †                                                                                 |
| 346  | CN_UINT32 | Postheater: running timers (bit set)             | 0=none, 2=timer 1 †                                                                                              |
| 369  | CN_UINT8  | Analog Input 0-10V 1                             | 0                                                                                                                |
| 370  | CN_UINT8  | Analog Input 0-10V 2                             | 0                                                                                                                |
| 371  | CN_UINT8  | Analog Input 0-10V 3                             | 0                                                                                                                |
| 372  | CN_UINT8  | Analog Input 0-10V 4                             | 0                                                                                                                |
| 384  | CN_INT16  |                                                  | 0.0                                                                                                              |
| 386  | CN_BOOL   |                                                  | 0                                                                                                                |
| 400  | CN_INT16  | ?? Temperature: after the Postheater             | value in °C, the same as 221 in every sample on a unit with a postheater                                         |
| 401  | CN_UINT8  | Postheater State                                 | value in % (0-100)                                                                                               |
| 402  | CN_BOOL   | Postheater Present                               | 0=absent, 1=present                                                                                              |
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

# Schedule PDOs

The ventilation unit has a SCHEDULE unit with one instance per setting that can be overridden (see
[Known schedules](PROTOCOL-RMI.md#known-schedules) in the RMI documentation). Each instance can be driven by a
week schedule of entries and by timers, and the unit reports the state of every instance in the same six PDOs:

`pdid = base + schedule instance`

| base | type      | meaning                                                                                                    |
|------|-----------|------------------------------------------------------------------------------------------------------------|
| 32   | CN_UINT8  | Active schedule entry: the id of the week schedule entry that is active now.                               |
| 48   | CN_UINT8  | Active timer: the id of the timer that is active now, `255` when no timer is active.                       |
| 64   | CN_UINT8  | Active value: the value the instance has now, with the same values as the timer value in the RMI command.  |
| 80   | CN_UINT32 | Remaining: the seconds left on the active timer, `4294967295` when it has no end or no timer is active.    |
| 320  | CN_UINT16 | Enabled schedule entries: a bit set, bit `n` is set when schedule entry `n` is enabled.                    |
| 336  | CN_UINT32 | Running timers: a bit set, bit `n` is set when timer `n` is running (so `2` is timer 1).                   |

| instance | constant                       | setting                               | 32 | 48 | 64 | 80 | 320 | 336 |
|----------|--------------------------------|---------------------------------------|----|----|----|----|-----|-----|
| 1        | `SCHEDULE_PRESET`              | Preset: fan speed, boost and away     | 33 | 49 | 65 | 81 | 321 | 337 |
| 2        | `SCHEDULE_BYPASS`              | Bypass                                | 34 | 50 | 66 | 82 | 322 | 338 |
| 3        | `SCHEDULE_TEMPERATURE_PROFILE` | Temperature profile (comfort profile) | 35 | 51 | 67 | 83 | 323 | 339 |
| 4        |                                | Standby                               | 36 | 52 | 68 | 84 | 324 | 340 |
| 5        | `SCHEDULE_COMFOCOOL`           | ComfoCool off                         | 37 | 53 | 69 | 85 | 325 | 341 |
| 6        | `SCHEDULE_SUPPLY_ONLY`         | Exhaust fan off, so supply only       | 38 | 54 | 70 | 86 | 326 | 342 |
| 7        | `SCHEDULE_EXHAUST_ONLY`        | Supply fan off, so exhaust only       | 39 | 55 | 71 | 87 | 327 | 343 |
| 8        | `SCHEDULE_MANUAL_MODE`         | Manual mode                           | 40 | 56 | 72 | 88 | 328 | 344 |
| 9        |                                | Hood (cooker hood mode)               | 41 | 57 | 73 | 89 | 329 | 345 |
| 10       |                                | Postheater                            | 42 | 58 | 74 | 90 | 330 | 346 |

The timer ids are the ones from the RMI table: `TIMER_DEFAULT` (`1`) for every instance, and for the preset
instance also `5` (manual mode), `TIMER_BOOST` (`6`) and `TIMER_AWAY` (`11`). That is why PDO 49 reads `6` during
boost and `11` while away, and why PDO 81 then holds the time left of that boost or away timer. The hood also has a
switch timer (`2`).

The values of the active value PDOs (base 64):

| instance            | values                               |
|---------------------|--------------------------------------|
| Preset              | 0=away, 1=low, 2=medium, 3=high      |
| Bypass              | 0=auto, 1=full, 2=none               |
| Temperature profile | 0=normal, 1=cool, 2=warm             |
| Standby             | 0=off, 1=on †                        |
| ComfoCool off       | 0=auto, 1=off                        |
| Exhaust fan off     | 0=fan runs, 1=fan off (supply only)  |
| Supply fan off      | 0=fan runs, 1=fan off (exhaust only) |
| Manual mode         | 0=off, 1=on †                        |
| Hood                | 0=off, 1=on †                        |
| Postheater          | 0=off, 1=heat †, 2=comfort †         |

How certain this is: the pattern and the types come from the official app, and were checked on a unit:

- All 60 pdids (10 instances × 6 bases) are sent by the unit.
- With the unit in auto and no timers running, base 48 is `255`, base 80 is `4294967295` and base 336 is `0` for
  every instance except the temperature profile (see below), base 64 is `0` except 65 (the fan speed), base 32 is `0` except 33 (`1`), and base 320 is `1`
  except 321 (`3`).
- A temperature profile timer without an end gave 51 = `1`, 339 = `2` and 83 = `4294967295`. So `4294967295` on base
  80 means "no end", either because no timer is active or because the active timer runs until it is cancelled.
- A boost of 60 seconds set 49 from `255` to `6`, 65 from `1` to `3` and 337 from `0` to `64`, and 81 counted down
  from `60` every second. Cancelling it brought 49, 65 and 337 back, and 81 to `4294967295`.

Right after subscribing, the bridge first sends `0` for some of these pdids (seen on 49 and 81) before the real
value, like for other sensors.

What is marked † was not exercised: the meaning of the schedule entry ids and bit sets (bases 32 and 320), and the
values of timers and states that were not active during the test, like the standby, hood and postheater states, or
`2048` on 337 for away (timer 11, by the same rule as `64` for boost).

# ComfoClime sensors

These pdids are only reported when a ComfoClime (productId `0x14`) is present on the ComfoNet bus. They were
reverse engineered from the ComfoClime's own HTTP API, which exposes them as "telemetry" ids. The entries
marked `??` have not been identified yet.

| pdid | type      | description                     | examples                            |
|------|-----------|---------------------------------|-------------------------------------|
| 4145 | CN_INT16  | TPMA Temperature                | value in °C (215 -> 21.5 °C)        |
| 4148 | CN_INT16  | Target Temperature              | value in °C (215 -> 21.5 °C)        |
| 4149 | CN_UINT8  | Device Mode                     | 0=off, 1=heating, 2=cooling         |
| 4151 | CN_INT16  | Current Comfort Temperature     | value in °C (215 -> 21.5 °C)        |
| 4154 | CN_INT16  | Indoor Temperature              | value in °C (215 -> 21.5 °C)        |
| 4193 | CN_INT16  | Temperature: Supply Air         | value in °C (215 -> 21.5 °C)        |
| 4194 | CN_INT16  | Temperature: Exhaust Air        | value in °C (215 -> 21.5 °C)        |
| 4195 | CN_INT16  | Temperature: Supply Coil        | value in °C (215 -> 21.5 °C)        |
| 4196 | CN_INT16  | Temperature: Exhaust Coil       | value in °C (215 -> 21.5 °C)        |
| 4197 | CN_INT16  | Temperature: Compressor         | value in °C (215 -> 21.5 °C)        |
| 4198 | CN_UINT8  | Heat Pump Duty                  | value in % (0-100)                  |
| 4201 | CN_UINT16 | Power Consumption: Heat Pump    | value in Watt                       |
| 4202 | CN_UINT16 | ??                              |                                     |
| 4203 | CN_UINT16 | ??                              |                                     |
| 4204 | CN_UINT16 | ??                              |                                     |
| 4205 | CN_UINT16 | ??                              |                                     |
| 4206 | CN_UINT16 | ??                              |                                     |
| 4207 | CN_UINT16 | ??                              |                                     |
| 4208 | CN_UINT16 | ??                              |                                     |
