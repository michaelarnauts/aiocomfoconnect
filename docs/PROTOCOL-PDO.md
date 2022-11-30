# PDO sensors

## PDO data types

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

| pdid | type      | description                                              | examples                                                    |
|------|-----------|----------------------------------------------------------|:------------------------------------------------------------|
| 16   | CN_UINT8  | Away indicator                                           | `01` = low, medium, high fan speed, `07` = away             |
| 18   | CN_UINT8  | Changing filters                                         | `01` = active, `02` = changing filter                       |
| 33   | CN_UINT8  |                                                          |                                                             |
| 37   | CN_UINT8  |                                                          |                                                             |
| 49   | CN_UINT8  | Operating mode                                           | `01` = limited manual, `05` = unlimited manual, `ff` = auto |
| 53   | CN_UINT8  |                                                          |                                                             |
| 54   | CN_UINT8  |                                                          |                                                             |
| 55   | CN_UINT8  |                                                          |                                                             |
| 56   | CN_UINT8  | Operating mode                                           | `01` = unlimited manual, `ff` = auto                        |
| 65   | CN_UINT8  | Fans: Fan speed setting                                  | `00` (away), `01`, `02` or `03`                             |
| 66   | CN_UINT8  | Bypass activation mode                                   | `00` = auto, `01` = activated, `02` = deactivated           |
| 67   | CN_UINT8  | Temperature Profile                                      | `00` = normal, `01` = cold, `02` = warm                     |
| 70   | CN_UINT8  | Supply Fan Mode                                          |                                                             |
| 71   | CN_UINT8  | Exhaust Fan Mode                                         |                                                             |
| 81   | CN_UINT32 | General: Countdown until next fan speed change           | `52020000` = 00000252 -> 594 seconds                        |
| 82   | CN_UINT32 | Bypass Next Change                                       |                                                             |
| 85   | CN_UINT32 |                                                          |                                                             |
| 86   | CN_UINT32 | Supply Fan Next Change                                   |                                                             |
| 87   | CN_UINT32 | Exhaust Fan Next Change                                  |                                                             |
| 117  | CN_UINT8  | Fans: Exhaust fan duty                                   | `1c` = 28%                                                  |
| 118  | CN_UINT8  | Fans: Supply fan duty                                    | `1d` = 29%                                                  |
| 119  | CN_UINT16 | Fans: Exhaust fan flow                                   | `6e00` = 110 m³/h                                           |
| 120  | CN_UINT16 | Fans: Supply fan flow                                    | `6900` = 105 m³/h                                           |
| 121  | CN_UINT16 | Fans: Exhaust fan speed                                  | `2d04` = 1069 rpm                                           |
| 122  | CN_UINT16 | Fans: Supply fan speed                                   | `5904` = 1113 rpm                                           |
| 128  | CN_UINT16 | Power Consumption: Current Ventilation                   | `0f00` = 15 W                                               |
| 129  | CN_UINT16 | Power Consumption: Total year-to-date                    | `1700` = 23 kWh                                             |
| 130  | CN_UINT16 | Power Consumption: Total from start                      | `1700` = 23 kWh                                             |
| 144  | CN_UINT16 | Preheater Power Consumption: Total year-to-date          | `1700` = 23 kWh                                             |
| 145  | CN_UINT16 | Preheater Power Consumption: Total from start            | `1700` = 23 kWh                                             |
| 146  | CN_UINT16 | Preheater Power Consumption: Current Ventilation         | `0f00` = 15 W                                               |
| 176  | CN_UINT8  | RF Pairing Mode                                          |                                                             |
| 192  | CN_UINT16 | Days left before filters must be replaced                | `8200` = 130 days                                           |
| 208  | CN_UINT8  | Device Temperature Unit                                  |                                                             |
| 209  | CN_INT16  | Running Mean Outdoor Temperature (RMOT)                  | `7500` = 117 -> 11.7 °C                                     |
| 210  | CN_BOOL   | Heating Season is active                                 |                                                             |
| 211  | CN_BOOL   | Cooling Season is active                                 |                                                             |
| 212  | CN_UINT8  | Temperature profile target                               | `ee00` = 23.8 °C                                            |
| 213  | CN_UINT16 | Avoided Heating: Avoided actual                          | `b901` = 441 -> 4.41 W                                      |
| 214  | CN_UINT16 | Avoided Heating: Avoided year-to-date                    | `dd01` = 477 kWh                                            |
| 215  | CN_UINT16 | Avoided Heating: Avoided total                           | `dd01` = 477 kWh                                            |
| 216  | CN_UINT16 | Avoided Cooling: Avoided actual                          | `b901` = 441 -> 4.41 W                                      |
| 217  | CN_UINT16 | Avoided Cooling: Avoided year-to-date                    | `dd01` = 477 kWh                                            |
| 218  | CN_UINT16 | Avoided Cooling: Avoided total                           | `dd01` = 477 kWh                                            |
| 219  | CN_UINT16 |                                                          |                                                             |
| 220  | CN_INT16  |                                                          |                                                             |
| 221  | CN_INT16  | Temperature & Humidity: Supply Air - PostHeaterTempAfter | `aa00` = 170 -> 17.0 °C                                     |
| 224  | CN_UINT8  | Device Airflow Unit                                      |                                                             |
| 225  | CN_UINT8  |                                                          |                                                             |
| 226  | CN_UINT16 | Fan Speed (modulated)                                    |                                                             |
| 227  | CN_UINT8  | Bypass state                                             | `64` = 100%                                                 |
| 228  | CN_UINT8  | ?? FrostProtectionUnbalance                              |                                                             |
| 274  | CN_INT16  | Temperature & Humidity: Extract Air                      | `ab00` = 171 -> 17.1 °C                                     |
| 275  | CN_INT16  | Temperature & Humidity: Exhaust Air                      | `5600` = 86 -> 8.6 °C                                       |
| 276  | CN_INT16  | Temperature & Humidity: Outdoor Air                      | `3c00` = 60 -> 6.0 °C                                       |
| 277  | CN_INT16  | Temperature & Humidity: Preheated Outdoor Air            | `3c00` = 60 -> 6.0 °C                                       |
| 278  | CN_INT16  | ?? PostHeaterTempBefore                                  |                                                             |
| 290  | CN_UINT8  | Temperature & Humidity: Extract Air                      | `31` = 49%                                                  |
| 291  | CN_UINT8  | Temperature & Humidity: Exhaust Air                      | `57` = 87%                                                  |
| 292  | CN_UINT8  | Temperature & Humidity: Outdoor Air                      | `43` = 67%                                                  |
| 293  | CN_UINT8  | Temperature & Humidity: Preheated Outdoor Air            | `43` = 67%                                                  |
| 294  | CN_UINT8  | Temperature & Humidity: Supply Air                       | `23` = 35%                                                  |
| 321  | CN_UINT16 |                                                          |                                                             |
| 325  | CN_UINT16 |                                                          |                                                             |
| 337  | CN_UINT32 |                                                          |                                                             |
| 338  | CN_UINT32 | Bypass Override                                          |                                                             |
| 341  | CN_UINT32 |                                                          |                                                             |
| 342  | CN_UINT32 |                                                          |                                                             |
| 343  | CN_UINT32 |                                                          |                                                             |
| 369  | CN_UINT8  |                                                          |                                                             |
| 370  | CN_UINT8  |                                                          |                                                             |
| 371  | CN_UINT8  |                                                          |                                                             |
| 372  | CN_UINT8  |                                                          |                                                             |
| 384  | CN_INT16  |                                                          |                                                             |
| 386  | CN_BOOL   |                                                          |                                                             |
| 400  | CN_INT16  |                                                          |                                                             |
| 401  | CN_UINT8  |                                                          |                                                             |
| 402  | CN_BOOL   | ?? PostHeaterPresent                                     |                                                             |
| 416  | CN_INT16  | ?? Outdoor air temperature                               |                                                             |
| 417  | CN_INT16  | ?? GHE Ground temperature                                |                                                             |
| 418  | CN_UINT8  | ?? GHE State                                             |                                                             |
| 419  | CN_BOOL   | ?? GHE Present                                           |                                                             |
| 784  | CN_UINT8  |                                                          |                                                             |
| 785  | CN_BOOL   | ?? ComfoCoolCompressor State                             |                                                             |
| 802  | CN_INT16  |                                                          |                                                             |
