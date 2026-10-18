""" Sensor definitions. """

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict

from .const import PdoType
from .util import calculate_airflow_constraints

# Sensors
SENSOR_AIRFLOW_CONSTRAINTS = 230
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
SENSOR_COMFOFOND_GHE_PRESENT = 419
SENSOR_COMFOFOND_GHE_STATE = 418
SENSOR_COMFOFOND_TEMP_GROUND = 417
SENSOR_COMFOFOND_TEMP_OUTDOOR = 416
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
SENSOR_POSTHEATER_PRESENT = 402
SENSOR_POSTHEATER_STATE = 401
SENSOR_POSTHEATER_TEMPERATURE_BEFORE = 278
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
SENSOR_COMFOCOOL_STATE = 784
SENSOR_COMFOCOOL_CONDENSOR_TEMP = 802

# The CO2 level of the CO2 sensors (ProductId.CO2SENSOR) in zone 1: SENSOR_CO2_1 is the one with the lowest node id.
SENSOR_CO2_1 = 1024
SENSOR_CO2_2 = 1025
SENSOR_CO2_3 = 1026
SENSOR_CO2_4 = 1027
SENSOR_CO2_5 = 1028
SENSOR_CO2_6 = 1029
SENSOR_CO2_7 = 1030
SENSOR_CO2_8 = 1031

# ComfoClime sensors. These are only reported when a ComfoClime is present on the ComfoNet bus.
SENSOR_COMFOCLIME_TPMA_TEMPERATURE = 4145
SENSOR_COMFOCLIME_TARGET_TEMPERATURE = 4148
SENSOR_COMFOCLIME_DEVICE_MODE = 4149
SENSOR_COMFOCLIME_COMFORT_TEMPERATURE = 4151
SENSOR_COMFOCLIME_INDOOR_TEMPERATURE = 4154
SENSOR_COMFOCLIME_TEMPERATURE_SUPPLY = 4193
SENSOR_COMFOCLIME_TEMPERATURE_EXHAUST = 4194
SENSOR_COMFOCLIME_TEMPERATURE_SUPPLY_COIL = 4195
SENSOR_COMFOCLIME_TEMPERATURE_EXHAUST_COIL = 4196
SENSOR_COMFOCLIME_TEMPERATURE_COMPRESSOR = 4197
SENSOR_COMFOCLIME_HEATPUMP_DUTY = 4198
SENSOR_COMFOCLIME_POWER_USAGE = 4201

UNIT_WATT = "W"
UNIT_KWH = "kWh"
UNIT_VOLT = "V"
UNIT_CELCIUS = "°C"
UNIT_PERCENT = "%"
UNIT_RPM = "rpm"
UNIT_M3H = "m³/h"
UNIT_PPM = "ppm"


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
    sensor.id: sensor
    for sensor in [
        Sensor("Device State", None, SENSOR_DEVICE_STATE, PdoType.TYPE_CN_UINT8),
        Sensor("Changing filters", None, SENSOR_CHANGING_FILTERS, PdoType.TYPE_CN_UINT8),
        Sensor("sensor_33", None, 33, PdoType.TYPE_CN_UINT8),
        Sensor("sensor_37", None, 37, PdoType.TYPE_CN_UINT8),
        Sensor("Operating Mode (preset timer)", None, SENSOR_OPERATING_MODE_2, PdoType.TYPE_CN_UINT8),
        Sensor("sensor_53", None, 53, PdoType.TYPE_CN_UINT8),
        Sensor("Supply Fan Mode (active timer)", None, SENSOR_FAN_MODE_SUPPLY_2, PdoType.TYPE_CN_UINT8),
        Sensor("Exhaust Fan Mode (active timer)", None, SENSOR_FAN_MODE_EXHAUST_2, PdoType.TYPE_CN_UINT8),
        Sensor("Operating Mode", None, SENSOR_OPERATING_MODE, PdoType.TYPE_CN_UINT8),
        Sensor("Fan Speed", None, SENSOR_FAN_SPEED_MODE, PdoType.TYPE_CN_UINT8),
        Sensor("Bypass Activation State", None, SENSOR_BYPASS_ACTIVATION_STATE, PdoType.TYPE_CN_UINT8),
        Sensor("Temperature Profile Mode", None, SENSOR_PROFILE_TEMPERATURE, PdoType.TYPE_CN_UINT8),
        Sensor("Supply Fan Mode", None, SENSOR_FAN_MODE_SUPPLY, PdoType.TYPE_CN_UINT8),
        Sensor("Exhaust Fan Mode", None, SENSOR_FAN_MODE_EXHAUST, PdoType.TYPE_CN_UINT8),
        Sensor("Fan Speed Next Change", None, SENSOR_NEXT_CHANGE_FAN, PdoType.TYPE_CN_UINT32),
        Sensor("Bypass Next Change", None, SENSOR_NEXT_CHANGE_BYPASS, PdoType.TYPE_CN_UINT32),
        Sensor("sensor_85", None, 85, PdoType.TYPE_CN_UINT32),
        Sensor("Supply Fan Next Change", None, SENSOR_NEXT_CHANGE_FAN_SUPPLY, PdoType.TYPE_CN_UINT32),
        Sensor("Exhaust Fan Next Change", None, SENSOR_NEXT_CHANGE_FAN_EXHAUST, PdoType.TYPE_CN_UINT32),
        Sensor("Exhaust Fan Duty", UNIT_PERCENT, SENSOR_FAN_EXHAUST_DUTY, PdoType.TYPE_CN_UINT8),
        Sensor("Supply Fan Duty", UNIT_PERCENT, SENSOR_FAN_SUPPLY_DUTY, PdoType.TYPE_CN_UINT8),
        Sensor("Exhaust Fan Flow", UNIT_M3H, SENSOR_FAN_EXHAUST_FLOW, PdoType.TYPE_CN_UINT16),
        Sensor("Supply Fan Flow", UNIT_M3H, SENSOR_FAN_SUPPLY_FLOW, PdoType.TYPE_CN_UINT16),
        Sensor("Exhaust Fan Speed", UNIT_RPM, SENSOR_FAN_EXHAUST_SPEED, PdoType.TYPE_CN_UINT16),
        Sensor("Supply Fan Speed", UNIT_RPM, SENSOR_FAN_SUPPLY_SPEED, PdoType.TYPE_CN_UINT16),
        Sensor("Power Usage", UNIT_WATT, SENSOR_POWER_USAGE, PdoType.TYPE_CN_UINT16),
        Sensor("Power Usage (year)", UNIT_KWH, SENSOR_POWER_USAGE_TOTAL_YEAR, PdoType.TYPE_CN_UINT16),
        Sensor("Power Usage (total)", UNIT_KWH, SENSOR_POWER_USAGE_TOTAL, PdoType.TYPE_CN_UINT16),
        Sensor("Preheater Power Usage (year)", UNIT_KWH, SENSOR_PREHEATER_POWER_TOTAL_YEAR, PdoType.TYPE_CN_UINT16),
        Sensor("Preheater Power Usage (total)", UNIT_KWH, SENSOR_PREHEATER_POWER_TOTAL, PdoType.TYPE_CN_UINT16),
        Sensor("Preheater Power Usage", UNIT_WATT, SENSOR_PREHEATER_POWER, PdoType.TYPE_CN_UINT16),
        Sensor("RF Pairing Mode", None, SENSOR_RF_PAIRING_MODE, PdoType.TYPE_CN_UINT8),
        Sensor("Days remaining to replace the filter", None, SENSOR_DAYS_TO_REPLACE_FILTER, PdoType.TYPE_CN_UINT16),
        Sensor("Device Temperature Unit", None, SENSOR_UNIT_TEMPERATURE, PdoType.TYPE_CN_UINT8, lambda x: {0: "celsius", 1: "fahrenheit"}.get(x, x)),
        Sensor("Running Mean Outdoor Temperature (RMOT)", UNIT_CELCIUS, SENSOR_RMOT, PdoType.TYPE_CN_INT16, lambda x: x / 10),
        Sensor("Heating Season is active", None, SENSOR_SEASON_HEATING_ACTIVE, PdoType.TYPE_CN_BOOL, bool),
        Sensor("Cooling Season is active", None, SENSOR_SEASON_COOLING_ACTIVE, PdoType.TYPE_CN_BOOL, bool),
        Sensor("Target Temperature", UNIT_CELCIUS, SENSOR_TARGET_TEMPERATURE, PdoType.TYPE_CN_INT16, lambda x: x / 10),
        Sensor("Avoided Heating Power Usage", UNIT_WATT, SENSOR_AVOIDED_HEATING, PdoType.TYPE_CN_UINT16),
        Sensor("Avoided Heating Power Usage (year)", UNIT_KWH, SENSOR_AVOIDED_HEATING_TOTAL_YEAR, PdoType.TYPE_CN_UINT16),
        Sensor("Avoided Heating Power Usage (total)", UNIT_KWH, SENSOR_AVOIDED_HEATING_TOTAL, PdoType.TYPE_CN_UINT16),
        Sensor("Avoided Cooling Power Usage", UNIT_WATT, SENSOR_AVOIDED_COOLING, PdoType.TYPE_CN_UINT16),
        Sensor("Avoided Cooling Power Usage (year)", UNIT_KWH, SENSOR_AVOIDED_COOLING_TOTAL_YEAR, PdoType.TYPE_CN_UINT16),
        Sensor("Avoided Cooling Power Usage (total)", UNIT_KWH, SENSOR_AVOIDED_COOLING_TOTAL, PdoType.TYPE_CN_UINT16),
        Sensor("sensor_219", None, 219, PdoType.TYPE_CN_UINT16),
        Sensor("Preheated Outdoor Air Temperature (?)", UNIT_CELCIUS, 220, PdoType.TYPE_CN_INT16, lambda x: x / 10),
        Sensor("Supply Air Temperature", UNIT_CELCIUS, SENSOR_TEMPERATURE_SUPPLY, PdoType.TYPE_CN_INT16, lambda x: x / 10),
        Sensor("Device Airflow Unit", None, SENSOR_UNIT_AIRFLOW, PdoType.TYPE_CN_UINT8, lambda x: {1: "kgph", 2: "lps", 3: "m3ph"}.get(x, x)),
        Sensor("Sensor based ventilation mode", None, SENSOR_COMFORTCONTROL_MODE, PdoType.TYPE_CN_UINT8),
        Sensor("Fan Speed (modulated)", None, SENSOR_FAN_SPEED_MODE_MODULATED, PdoType.TYPE_CN_UINT16),
        Sensor("Bypass State", UNIT_PERCENT, SENSOR_BYPASS_STATE, PdoType.TYPE_CN_UINT8),
        Sensor("frostprotection_unbalance", None, SENSOR_FROSTPROTECTION_UNBALANCE, PdoType.TYPE_CN_UINT8),
        Sensor("Airflow constraints", None, SENSOR_AIRFLOW_CONSTRAINTS, PdoType.TYPE_CN_INT64, calculate_airflow_constraints),
        Sensor("Extract Air Temperature", UNIT_CELCIUS, SENSOR_TEMPERATURE_EXTRACT, PdoType.TYPE_CN_INT16, lambda x: x / 10),
        Sensor("Exhaust Air Temperature", UNIT_CELCIUS, SENSOR_TEMPERATURE_EXHAUST, PdoType.TYPE_CN_INT16, lambda x: x / 10),
        Sensor("Outdoor Air Temperature", UNIT_CELCIUS, SENSOR_TEMPERATURE_OUTDOOR, PdoType.TYPE_CN_INT16, lambda x: x / 10),
        Sensor("Outdoor Air Temperature (?)", UNIT_CELCIUS, 277, PdoType.TYPE_CN_INT16, lambda x: x / 10),
        Sensor("Temperature before Postheater", UNIT_CELCIUS, SENSOR_POSTHEATER_TEMPERATURE_BEFORE, PdoType.TYPE_CN_INT16, lambda x: x / 10),
        Sensor("Extract Air Humidity", UNIT_PERCENT, SENSOR_HUMIDITY_EXTRACT, PdoType.TYPE_CN_UINT8),
        Sensor("Exhaust Air Humidity", UNIT_PERCENT, SENSOR_HUMIDITY_EXHAUST, PdoType.TYPE_CN_UINT8),
        Sensor("Outdoor Air Humidity", UNIT_PERCENT, SENSOR_HUMIDITY_OUTDOOR, PdoType.TYPE_CN_UINT8),
        Sensor("Outdoor Air Humidity (after preheater)", UNIT_PERCENT, SENSOR_HUMIDITY_AFTER_PREHEATER, PdoType.TYPE_CN_UINT8),
        Sensor("Supply Air Humidity", UNIT_PERCENT, SENSOR_HUMIDITY_SUPPLY, PdoType.TYPE_CN_UINT8),
        Sensor("sensor_321", None, 321, PdoType.TYPE_CN_UINT16),
        Sensor("sensor_325", None, 325, PdoType.TYPE_CN_UINT16),
        Sensor("sensor_337", None, 337, PdoType.TYPE_CN_UINT32),
        Sensor("Bypass Override", None, SENSOR_BYPASS_OVERRIDE, PdoType.TYPE_CN_UINT32),
        Sensor("sensor_341", None, 341, PdoType.TYPE_CN_UINT32),
        Sensor("Supply Fan Mode (running timers)", None, SENSOR_FAN_MODE_SUPPLY_3, PdoType.TYPE_CN_UINT32),
        Sensor("Exhaust Fan Mode (running timers)", None, SENSOR_FAN_MODE_EXHAUST_3, PdoType.TYPE_CN_UINT32),
        Sensor("Analog Input 1", UNIT_VOLT, SENSOR_ANALOG_INPUT_1, PdoType.TYPE_CN_UINT8, lambda x: x / 10),
        Sensor("Analog Input 2", UNIT_VOLT, SENSOR_ANALOG_INPUT_2, PdoType.TYPE_CN_UINT8, lambda x: x / 10),
        Sensor("Analog Input 3", UNIT_VOLT, SENSOR_ANALOG_INPUT_3, PdoType.TYPE_CN_UINT8, lambda x: x / 10),
        Sensor("Analog Input 4", UNIT_VOLT, SENSOR_ANALOG_INPUT_4, PdoType.TYPE_CN_UINT8, lambda x: x / 10),
        Sensor("sensor_384", None, 384, PdoType.TYPE_CN_INT16, lambda x: x / 10),
        Sensor("sensor_386", None, 386, PdoType.TYPE_CN_BOOL, bool),
        Sensor("sensor_400", None, 400, PdoType.TYPE_CN_INT16, lambda x: x / 10),
        Sensor("Postheater State", UNIT_PERCENT, SENSOR_POSTHEATER_STATE, PdoType.TYPE_CN_UINT8),
        Sensor("Postheater Present", None, SENSOR_POSTHEATER_PRESENT, PdoType.TYPE_CN_BOOL, bool),
        Sensor("ComfoFond Outdoor Air Temperature", UNIT_CELCIUS, SENSOR_COMFOFOND_TEMP_OUTDOOR, PdoType.TYPE_CN_INT16, lambda x: x / 10),
        Sensor("ComfoFond Ground Temperature", UNIT_CELCIUS, SENSOR_COMFOFOND_TEMP_GROUND, PdoType.TYPE_CN_INT16, lambda x: x / 10),
        Sensor("ComfoFond GHE State Percentage", UNIT_PERCENT, SENSOR_COMFOFOND_GHE_STATE, PdoType.TYPE_CN_UINT8),
        Sensor("ComfoFond GHE Present", None, SENSOR_COMFOFOND_GHE_PRESENT, PdoType.TYPE_CN_BOOL, bool),
        Sensor("ComfoCool State", None, SENSOR_COMFOCOOL_STATE, PdoType.TYPE_CN_UINT8),
        Sensor("sensor_785", None, 785, PdoType.TYPE_CN_BOOL, bool),
        Sensor("ComfoCool Condensor Temperature", UNIT_CELCIUS, SENSOR_COMFOCOOL_CONDENSOR_TEMP, PdoType.TYPE_CN_INT16, lambda x: x / 10),
        Sensor("CO2 Sensor 1", UNIT_PPM, SENSOR_CO2_1, PdoType.TYPE_CN_UINT16),
        Sensor("CO2 Sensor 2", UNIT_PPM, SENSOR_CO2_2, PdoType.TYPE_CN_UINT16),
        Sensor("CO2 Sensor 3", UNIT_PPM, SENSOR_CO2_3, PdoType.TYPE_CN_UINT16),
        Sensor("CO2 Sensor 4", UNIT_PPM, SENSOR_CO2_4, PdoType.TYPE_CN_UINT16),
        Sensor("CO2 Sensor 5", UNIT_PPM, SENSOR_CO2_5, PdoType.TYPE_CN_UINT16),
        Sensor("CO2 Sensor 6", UNIT_PPM, SENSOR_CO2_6, PdoType.TYPE_CN_UINT16),
        Sensor("CO2 Sensor 7", UNIT_PPM, SENSOR_CO2_7, PdoType.TYPE_CN_UINT16),
        Sensor("CO2 Sensor 8", UNIT_PPM, SENSOR_CO2_8, PdoType.TYPE_CN_UINT16),
        Sensor("ComfoClime TPMA Temperature", UNIT_CELCIUS, SENSOR_COMFOCLIME_TPMA_TEMPERATURE, PdoType.TYPE_CN_INT16, lambda x: x / 10),
        Sensor("ComfoClime Target Temperature", UNIT_CELCIUS, SENSOR_COMFOCLIME_TARGET_TEMPERATURE, PdoType.TYPE_CN_INT16, lambda x: x / 10),
        Sensor("ComfoClime Device Mode", None, SENSOR_COMFOCLIME_DEVICE_MODE, PdoType.TYPE_CN_UINT8),
        Sensor("ComfoClime Comfort Temperature", UNIT_CELCIUS, SENSOR_COMFOCLIME_COMFORT_TEMPERATURE, PdoType.TYPE_CN_INT16, lambda x: x / 10),
        Sensor("ComfoClime Indoor Temperature", UNIT_CELCIUS, SENSOR_COMFOCLIME_INDOOR_TEMPERATURE, PdoType.TYPE_CN_INT16, lambda x: x / 10),
        Sensor("ComfoClime Supply Air Temperature", UNIT_CELCIUS, SENSOR_COMFOCLIME_TEMPERATURE_SUPPLY, PdoType.TYPE_CN_INT16, lambda x: x / 10),
        Sensor("ComfoClime Exhaust Air Temperature", UNIT_CELCIUS, SENSOR_COMFOCLIME_TEMPERATURE_EXHAUST, PdoType.TYPE_CN_INT16, lambda x: x / 10),
        Sensor("ComfoClime Supply Coil Temperature", UNIT_CELCIUS, SENSOR_COMFOCLIME_TEMPERATURE_SUPPLY_COIL, PdoType.TYPE_CN_INT16, lambda x: x / 10),
        Sensor("ComfoClime Exhaust Coil Temperature", UNIT_CELCIUS, SENSOR_COMFOCLIME_TEMPERATURE_EXHAUST_COIL, PdoType.TYPE_CN_INT16, lambda x: x / 10),
        Sensor("ComfoClime Compressor Temperature", UNIT_CELCIUS, SENSOR_COMFOCLIME_TEMPERATURE_COMPRESSOR, PdoType.TYPE_CN_INT16, lambda x: x / 10),
        Sensor("ComfoClime Heat Pump Duty", UNIT_PERCENT, SENSOR_COMFOCLIME_HEATPUMP_DUTY, PdoType.TYPE_CN_UINT8),
        Sensor("ComfoClime Power Usage", UNIT_WATT, SENSOR_COMFOCLIME_POWER_USAGE, PdoType.TYPE_CN_UINT16),
        Sensor("sensor_4202", None, 4202, PdoType.TYPE_CN_UINT16),
        Sensor("sensor_4203", None, 4203, PdoType.TYPE_CN_UINT16),
        Sensor("sensor_4204", None, 4204, PdoType.TYPE_CN_UINT16),
        Sensor("sensor_4205", None, 4205, PdoType.TYPE_CN_UINT16),
        Sensor("sensor_4206", None, 4206, PdoType.TYPE_CN_UINT16),
        Sensor("sensor_4207", None, 4207, PdoType.TYPE_CN_UINT16),
        Sensor("sensor_4208", None, 4208, PdoType.TYPE_CN_UINT16),
    ]
}
