""" Sensor definitions. """
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict

from .util import calculate_airflow_constraints
from .const import (
    TYPE_CN_BOOL,
    TYPE_CN_INT16,
    TYPE_CN_UINT8,
    TYPE_CN_UINT16,
    TYPE_CN_UINT32,
    TYPE_CN_INT64,
)

# Sensors
SENSOR_ANALOG_INPUT_1 = 369
SENSOR_ANALOG_INPUT_2 = 370
SENSOR_ANALOG_INPUT_3 = 371
SENSOR_ANALOG_INPUT_4 = 372
SENSOR_AVOIDED_COOLING = 216
SENSOR_AVOIDED_COOLING_TOTAL = 218
SENSOR_AVOIDED_COOLING_TOTAL_YEAR = 217
SENSOR_AVOIDED_HEATING = 213
SENSOR_AVOIDED_HEATING_TOTAL = 215
SENSOR_AVOIDED_HEATING_TOTAL_YEAR = 214
SENSOR_BYPASS_ACTIVATION_STATE = 66
SENSOR_BYPASS_OVERRIDE = 338
SENSOR_BYPASS_STATE = 227
SENSOR_CHANGING_FILTERS = 18
SENSOR_COMFORTCONTROL_MODE = 225
SENSOR_DAYS_TO_REPLACE_FILTER = 192
SENSOR_DEVICE_STATE = 16
SENSOR_FAN_EXHAUST_DUTY = 117
SENSOR_FAN_EXHAUST_FLOW = 119
SENSOR_FAN_EXHAUST_SPEED = 121
SENSOR_FAN_MODE_EXHAUST = 71
SENSOR_FAN_MODE_EXHAUST_2 = 55
SENSOR_FAN_MODE_EXHAUST_3 = 343
SENSOR_FAN_MODE_SUPPLY = 70
SENSOR_FAN_MODE_SUPPLY_2 = 54
SENSOR_FAN_MODE_SUPPLY_3 = 342
SENSOR_FAN_SPEED_MODE = 65
SENSOR_FAN_SPEED_MODE_MODULATED = 226
SENSOR_FAN_SUPPLY_DUTY = 118
SENSOR_FAN_SUPPLY_FLOW = 120
SENSOR_FAN_SUPPLY_SPEED = 122
SENSOR_FROSTPROTECTION_UNBALANCE = 228
SENSOR_HUMIDITY_AFTER_PREHEATER = 293
SENSOR_HUMIDITY_EXHAUST = 291
SENSOR_HUMIDITY_EXTRACT = 290
SENSOR_HUMIDITY_OUTDOOR = 292
SENSOR_HUMIDITY_SUPPLY = 294
SENSOR_NEXT_CHANGE_BYPASS = 82
SENSOR_NEXT_CHANGE_FAN = 81
SENSOR_NEXT_CHANGE_FAN_EXHAUST = 87
SENSOR_NEXT_CHANGE_FAN_SUPPLY = 86
SENSOR_OPERATING_MODE = 56
SENSOR_OPERATING_MODE_2 = 49
SENSOR_POWER_USAGE = 128
SENSOR_POWER_USAGE_TOTAL = 130
SENSOR_POWER_USAGE_TOTAL_YEAR = 129
SENSOR_PREHEATER_POWER = 146
SENSOR_PREHEATER_POWER_TOTAL = 145
SENSOR_PREHEATER_POWER_TOTAL_YEAR = 144
SENSOR_PROFILE_TEMPERATURE = 67
SENSOR_RF_PAIRING_MODE = 176
SENSOR_RMOT = 209
SENSOR_SEASON_COOLING_ACTIVE = 211
SENSOR_SEASON_HEATING_ACTIVE = 210
SENSOR_TARGET_TEMPERATURE = 212
SENSOR_TEMPERATURE_EXHAUST = 275
SENSOR_TEMPERATURE_EXTRACT = 274
SENSOR_TEMPERATURE_OUTDOOR = 276
SENSOR_TEMPERATURE_SUPPLY = 221
SENSOR_UNIT_AIRFLOW = 224
SENSOR_UNIT_TEMPERATURE = 208
SENSOR_AIRFLOW_CONSTRAINTS = 230

UNIT_WATT = "W"
UNIT_KWH = "kWh"
UNIT_CELCIUS = "°C"
UNIT_PERCENT = "%"
UNIT_RPM = "rpm"
UNIT_M3H = "m³/h"


@dataclass
class Sensor:
    """Dataclass for a Sensor"""

    name: str
    unit: str | None
    id: int  # pylint: disable=invalid-name
    type: int
    value_fn: Callable[[int], any] = None


# For more information, see PROTOCOL-PDO.md
SENSORS: Dict[int, Sensor] = {
    SENSOR_DEVICE_STATE: Sensor("Device State", None, 16, TYPE_CN_UINT8),
    SENSOR_CHANGING_FILTERS: Sensor("Changing filters", None, 18, TYPE_CN_UINT8),
    33: Sensor("sensor_33", None, 33, TYPE_CN_UINT8),
    37: Sensor("sensor_37", None, 37, TYPE_CN_UINT8),
    SENSOR_OPERATING_MODE_2: Sensor("Operating Mode", None, 49, TYPE_CN_UINT8),
    53: Sensor("sensor_53", None, 53, TYPE_CN_UINT8),
    SENSOR_FAN_MODE_SUPPLY_2: Sensor("Supply Fan Mode", None, 54, TYPE_CN_UINT8),
    SENSOR_FAN_MODE_EXHAUST_2: Sensor("Exhaust Fan Mode", None, 55, TYPE_CN_UINT8),
    SENSOR_OPERATING_MODE: Sensor("Operating Mode", None, 56, TYPE_CN_UINT8),
    SENSOR_FAN_SPEED_MODE: Sensor("Fan Speed", None, 65, TYPE_CN_UINT8),
    SENSOR_BYPASS_ACTIVATION_STATE: Sensor("Bypass Activation State", None, 66, TYPE_CN_UINT8),
    SENSOR_PROFILE_TEMPERATURE: Sensor("Temperature Profile Mode", None, 67, TYPE_CN_UINT8),
    SENSOR_FAN_MODE_SUPPLY: Sensor("Supply Fan Mode", None, 70, TYPE_CN_UINT8),
    SENSOR_FAN_MODE_EXHAUST: Sensor("Exhaust Fan Mode", None, 71, TYPE_CN_UINT8),
    SENSOR_NEXT_CHANGE_FAN: Sensor("Fan Speed Next Change", None, 81, TYPE_CN_UINT32),
    SENSOR_NEXT_CHANGE_BYPASS: Sensor("Bypass Next Change", None, 82, TYPE_CN_UINT32),
    85: Sensor("sensor_85", None, 85, TYPE_CN_UINT32),
    SENSOR_NEXT_CHANGE_FAN_SUPPLY: Sensor("Supply Fan Next Change", None, 86, TYPE_CN_UINT32),
    SENSOR_NEXT_CHANGE_FAN_EXHAUST: Sensor("Exhaust Fan Next Change", None, 87, TYPE_CN_UINT32),
    SENSOR_FAN_EXHAUST_DUTY: Sensor("Exhaust Fan Duty", UNIT_PERCENT, 117, TYPE_CN_UINT8),
    SENSOR_FAN_SUPPLY_DUTY: Sensor("Supply Fan Duty", UNIT_PERCENT, 118, TYPE_CN_UINT8),
    SENSOR_FAN_EXHAUST_FLOW: Sensor("Exhaust Fan Flow", UNIT_M3H, 119, TYPE_CN_UINT16),
    SENSOR_FAN_SUPPLY_FLOW: Sensor("Supply Fan Flow", UNIT_M3H, 120, TYPE_CN_UINT16),
    SENSOR_FAN_EXHAUST_SPEED: Sensor("Exhaust Fan Speed", UNIT_RPM, 121, TYPE_CN_UINT16),
    SENSOR_FAN_SUPPLY_SPEED: Sensor("Supply Fan Speed", UNIT_RPM, 122, TYPE_CN_UINT16),
    SENSOR_POWER_USAGE: Sensor("Power Usage", UNIT_WATT, 128, TYPE_CN_UINT16),
    SENSOR_POWER_USAGE_TOTAL_YEAR: Sensor("Power Usage (year)", UNIT_KWH, 129, TYPE_CN_UINT16),
    SENSOR_POWER_USAGE_TOTAL: Sensor("Power Usage (total)", UNIT_KWH, 130, TYPE_CN_UINT16),
    SENSOR_PREHEATER_POWER_TOTAL_YEAR: Sensor("Preheater Power Usage (year)", UNIT_KWH, 144, TYPE_CN_UINT16),
    SENSOR_PREHEATER_POWER_TOTAL: Sensor("Preheater Power Usage (total)", UNIT_KWH, 145, TYPE_CN_UINT16),
    SENSOR_PREHEATER_POWER: Sensor("Preheater Power Usage", UNIT_WATT, 146, TYPE_CN_UINT16),
    SENSOR_RF_PAIRING_MODE: Sensor("RF Pairing Mode", None, 176, TYPE_CN_UINT8),
    SENSOR_DAYS_TO_REPLACE_FILTER: Sensor("Days remaining to replace the filter", None, 192, TYPE_CN_UINT16),
    SENSOR_UNIT_TEMPERATURE: Sensor("Device Temperature Unit", None, 208, TYPE_CN_UINT8, lambda x: "celcius" if x == 0 else "farenheit"),
    SENSOR_RMOT: Sensor("Running Mean Outdoor Temperature (RMOT)", UNIT_CELCIUS, 209, TYPE_CN_INT16, lambda x: x / 10),
    SENSOR_SEASON_HEATING_ACTIVE: Sensor("Heating Season is active", None, 210, TYPE_CN_BOOL, bool),
    SENSOR_SEASON_COOLING_ACTIVE: Sensor("Cooling Season is active", None, 211, TYPE_CN_BOOL, bool),
    SENSOR_TARGET_TEMPERATURE: Sensor("Target Temperature", UNIT_CELCIUS, 212, TYPE_CN_INT16, lambda x: x / 10),
    SENSOR_AVOIDED_HEATING: Sensor("Avoided Heating Power Usage", UNIT_WATT, 213, TYPE_CN_UINT16),
    SENSOR_AVOIDED_HEATING_TOTAL_YEAR: Sensor("Avoided Heating Power Usage (year)", UNIT_KWH, 214, TYPE_CN_UINT16),
    SENSOR_AVOIDED_HEATING_TOTAL: Sensor("Avoided Heating Power Usage (total)", UNIT_KWH, 215, TYPE_CN_UINT16),
    SENSOR_AVOIDED_COOLING: Sensor("Avoided Cooling Power Usage", UNIT_WATT, 216, TYPE_CN_UINT16),
    SENSOR_AVOIDED_COOLING_TOTAL_YEAR: Sensor("Avoided Cooling Power Usage (year)", UNIT_KWH, 217, TYPE_CN_UINT16),
    SENSOR_AVOIDED_COOLING_TOTAL: Sensor("Avoided Cooling Power Usage (total)", UNIT_KWH, 218, TYPE_CN_UINT16),
    219: Sensor("sensor_219", None, 219, TYPE_CN_UINT16),
    220: Sensor("Outdoor Air Temperature (?)", None, 220, TYPE_CN_INT16, lambda x: x / 10),
    SENSOR_TEMPERATURE_SUPPLY: Sensor("Supply Air Temperature", UNIT_CELCIUS, 221, TYPE_CN_INT16, lambda x: x / 10),
    SENSOR_UNIT_AIRFLOW: Sensor("Device Airflow Unit", None, 224, TYPE_CN_UINT8, lambda x: "m3ph" if x == 3 else "lps"),
    SENSOR_COMFORTCONTROL_MODE: Sensor("Sensor based ventilation mode", None, 225, TYPE_CN_UINT8),
    SENSOR_FAN_SPEED_MODE_MODULATED: Sensor("Fan Speed (modulated)", None, 226, TYPE_CN_UINT16),
    SENSOR_BYPASS_STATE: Sensor("Bypass State", UNIT_PERCENT, 227, TYPE_CN_UINT8),
    SENSOR_FROSTPROTECTION_UNBALANCE: Sensor("frostprotection_unbalance", None, 228, TYPE_CN_UINT8),
    SENSOR_AIRFLOW_CONSTRAINTS: Sensor("Airflow constraints", None, 230, TYPE_CN_INT64, calculate_airflow_constraints),
    SENSOR_TEMPERATURE_EXTRACT: Sensor("Extract Air Temperature", UNIT_CELCIUS, 274, TYPE_CN_INT16, lambda x: x / 10),
    SENSOR_TEMPERATURE_EXHAUST: Sensor("Exhaust Air Temperature", UNIT_CELCIUS, 275, TYPE_CN_INT16, lambda x: x / 10),
    SENSOR_TEMPERATURE_OUTDOOR: Sensor("Outdoor Air Temperature", UNIT_CELCIUS, 276, TYPE_CN_INT16, lambda x: x / 10),
    277: Sensor("Outdoor Air Temperature (?)", UNIT_CELCIUS, 277, TYPE_CN_INT16, lambda x: x / 10),
    278: Sensor("Supply Air Temperature (?)", UNIT_CELCIUS, 278, TYPE_CN_INT16, lambda x: x / 10),
    SENSOR_HUMIDITY_EXTRACT: Sensor("Extract Air Humidity", UNIT_PERCENT, 290, TYPE_CN_UINT8),
    SENSOR_HUMIDITY_EXHAUST: Sensor("Exhaust Air Humidity", UNIT_PERCENT, 291, TYPE_CN_UINT8),
    SENSOR_HUMIDITY_OUTDOOR: Sensor("Outdoor Air Humidity", UNIT_PERCENT, 292, TYPE_CN_UINT8),
    SENSOR_HUMIDITY_AFTER_PREHEATER: Sensor("Outdoor Air Humidity (after preheater)", UNIT_PERCENT, 293, TYPE_CN_UINT8),
    SENSOR_HUMIDITY_SUPPLY: Sensor("Supply Air Humidity", UNIT_PERCENT, 294, TYPE_CN_UINT8),
    321: Sensor("sensor_321", None, 321, TYPE_CN_UINT16),
    325: Sensor("sensor_325", None, 325, TYPE_CN_UINT16),
    337: Sensor("sensor_337", None, 337, TYPE_CN_UINT32),
    SENSOR_BYPASS_OVERRIDE: Sensor("Bypass Override", None, 338, TYPE_CN_UINT32),
    341: Sensor("sensor_341", None, 341, TYPE_CN_UINT32),
    SENSOR_FAN_MODE_SUPPLY_3: Sensor("Supply Fan Mode", None, 342, TYPE_CN_UINT32),
    SENSOR_FAN_MODE_EXHAUST_3: Sensor("Exhaust Fan Mode", None, 343, TYPE_CN_UINT32),
    SENSOR_ANALOG_INPUT_1: Sensor("Analog Input 1", None, 369, TYPE_CN_UINT8),
    SENSOR_ANALOG_INPUT_2: Sensor("Analog Input 2", None, 370, TYPE_CN_UINT8),
    SENSOR_ANALOG_INPUT_3: Sensor("Analog Input 3", None, 371, TYPE_CN_UINT8),
    SENSOR_ANALOG_INPUT_4: Sensor("Analog Input 4", None, 372, TYPE_CN_UINT8),
    384: Sensor("sensor_384", None, 384, TYPE_CN_INT16, lambda x: x / 10),
    386: Sensor("sensor_386", None, 386, TYPE_CN_BOOL, bool),
    400: Sensor("sensor_400", None, 400, TYPE_CN_INT16, lambda x: x / 10),
    401: Sensor("sensor_401", None, 401, TYPE_CN_UINT8),
    402: Sensor("sensor_402", None, 402, TYPE_CN_BOOL, bool),
    416: Sensor("sensor_416", None, 416, TYPE_CN_INT16, lambda x: x / 10),
    417: Sensor("sensor_417", None, 417, TYPE_CN_INT16, lambda x: x / 10),
    418: Sensor("sensor_418", None, 418, TYPE_CN_UINT8),
    419: Sensor("sensor_419", None, 419, TYPE_CN_BOOL, bool),
    784: Sensor("sensor_784", None, 784, TYPE_CN_UINT8),
    785: Sensor("sensor_785", None, 785, TYPE_CN_BOOL),
    802: Sensor("sensor_802", None, 802, TYPE_CN_INT16, lambda x: x / 10),
}
