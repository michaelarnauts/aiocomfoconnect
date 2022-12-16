""" Constants """

# PDO Types
TYPE_CN_BOOL = 0x00
TYPE_CN_UINT8 = 0x01
TYPE_CN_UINT16 = 0x02
TYPE_CN_UINT32 = 0x03
TYPE_CN_INT8 = 0x05
TYPE_CN_INT16 = 0x06
TYPE_CN_INT64 = 0x08
TYPE_CN_STRING = 0x09
TYPE_CN_TIME = 0x10
TYPE_CN_VERSION = 0x11


# ComfoConnect Units
UNIT_NODE = 0x01
UNIT_COMFOBUS = 0x02
UNIT_ERROR = 0x03
UNIT_SCHEDULE = 0x15
UNIT_VALVE = 0x16
UNIT_FAN = 0x17
UNIT_POWERSENSOR = 0x18
UNIT_PREHEATER = 0x19
UNIT_HMI = 0x1A
UNIT_RFCOMMUNICATION = 0x1B
UNIT_FILTER = 0x1C
UNIT_TEMPHUMCONTROL = 0x1D
UNIT_VENTILATIONCONFIG = 0x1E
UNIT_NODECONFIGURATION = 0x20
UNIT_TEMPERATURESENSOR = 0x21
UNIT_HUMIDITYSENSOR = 0x22
UNIT_PRESSURESENSOR = 0x23
UNIT_PERIPHERALS = 0x24
UNIT_ANALOGINPUT = 0x25
UNIT_COOKERHOOD = 0x26
UNIT_POSTHEATER = 0x27
UNIT_COMFOFOND = 0x28
UNIT_CO2SENSOR = 0x2B
UNIT_SERVICEPRINT = 0x2C
# UNIT_COOLER(21) = 0x15
# UNIT_CC_TEMPERATURESENSOR(22) = 0x16
# UNIT_IOSENSOR(21) = 0x15
# UNIT_CONNECTIONBOARD_IOSENSOR(21) = 0x15
# UNIT_CONNECTIONBOARD_NODECONFIGURATION(22) = 0x16
# UNIT_CONNECTIONBOARD_WIFI(23) = 0x17
# UNIT_CO2SENSOR_CO2SENSOR(21) = 0x15
# UNIT_CO2SENSOR_TEMPERATURESENSOR(22) = 0x16
# UNIT_CO2SENSOR_HUMIDITYSENSOR(23) = 0x17
# UNIT_CO2SENSOR_ENVPRESSURESENSOR(24) = 0x18
# UNIT_CO2SENSOR_HMI(25) = 0x19

SUBUNIT_01 = 0x01
SUBUNIT_02 = 0x02
SUBUNIT_03 = 0x03
SUBUNIT_04 = 0x04
SUBUNIT_05 = 0x05
SUBUNIT_06 = 0x06
SUBUNIT_07 = 0x07
SUBUNIT_08 = 0x08

ERRORS_BASE = {
    21: "DANGER! OVERHEATING! Two or more sensors are detecting an incorrect temperature. Ventilation has stopped.",
    22: "Temperature too high for ComfoAir Q (TEMP_HRU ERROR)",
    23: "The extract air temperature sensor has a malfunction (SENSOR_ETA ERROR)",
    24: "The extract air temperature sensor is detecting an incorrect temperature (TEMP_SENSOR_ETA ERROR)",
    25: "The exhaust air temperature sensor has a malfunction (SENSOR_EHA ERROR)",
    26: "The exhaust air temperature sensor is detecting an incorrect temperature (TEMP_SENSOR_EHA ERROR)",
    27: "The outdoor air temperature sensor has a malfunction (SENSOR_ODA ERROR)",
    28: "The outdoor air temperature sensor is detecting an incorrect temperature (TEMP_SENSOR_ODA ERROR)",
    29: "The pre-conditioned outdoor air temperature sensor has a malfunction",
    30: "The pre-conditioned outdoor air temperature sensor is detecting an incorrect temperature (TEMP_SENSOR_P-ODA ERROR)",
    31: "The supply air temperature sensor has a malfunction (SENSOR_SUP ERROR)",
    32: "The supply air temperature sensor is detecting an incorrect temperature (TEMP_SENSOR_SUP ERROR)",
    33: "The Ventilation Unit has not been commissioned (INIT ERROR)",
    34: "The front door is open",
    35: "The Pre-heater is present, but not in the correct position (right/left). (PREHEAT_LOCATION ERROR)",
    37: "The pre-heater has a malfunction (PREHEAT ERROR)",
    38: "The pre-heater has a malfunction (PREHEAT ERROR)",
    39: "The extract air humidity sensor has a malfunction (SENSOR_ETA ERROR)",
    41: "The exhaust air humidity sensor has a malfunction (SENSOR_EHA ERROR)",
    43: "The outdoor air humidity sensor has a malfunction (SENSOR_ODA ERROR)",
    45: "The outdoor air humidity sensor has a malfunction (SENSOR_P-ODA ERROR)",
    47: "The supply air humidity sensor has a malfunction (SENSOR_SUP ERROR)",
    49: "The exhaust air flow sensor has a malfunction (SENSOR_EHA ERROR)",
    50: "The supply air flow sensor has a malfunction (SENSOR_SUP ERROR)",
    51: "The extract air fan has a malfunction (FAN_EHA ERROR)",
    52: "The supply air fan has a malfunction (FAN_SUP ERROR)",
    53: "Exhaust air pressure too high. Check air outlets, ducts and filters for pollution and obstructions. Check valve settings (EXT_PRESSURE_EHA ERROR)",
    54: "Supply air pressure too high. Check air outlets, ducts and filters for pollution and obstructions. Check valve settings. (EXT_PRESSURE_SUP ERROR)",
    55: "The extract air fan has a malfunction (FAN_EHA ERROR)",
    56: "The supply air fan has a malfunction (FAN_SUP ERROR)",
    57: "The exhaust air flow is not reaching its set point (AIRFLOW_EHA ERROR)",
    58: "The supply air flow is not reaching its set point (AIRFLOW_SUP ERROR)",
    59: "Failed to reach required temperature too often for outdoor air after pre-heater (TEMPCONTROL_P-ODA ERROR)",
    60: "Failed to reach required temperature too often for supply air. The modulating by-pass may have a malfunction. (TEMPCONTROL_SUP ERROR)",
    61: "Supply air temperature is too low too often (TEMP_SUP_MIN ERROR)",
    62: "Unbalance occurred too often beyond tolerance levels in past period (UNBALANCE ERROR)",
    63: "Postheater was present, but is no longer detected (POSTHEAT_CONNECT ERROR)",
    64: "Temperature sensor value for supply air ComfoCool exceeded limit too often (CCOOL_TEMP ERROR)",
    65: "Room temperature sensor was present, but is no longer detected (T_ROOM_PRES ERROR)",
    66: "RF Communication hardware was present, but is no longer detected (RF_PRES ERROR)",
    67: "Option Box was present, but is no longer detected (OPTION_BOX CONNECT ERROR)",
    68: "Pre-heater was present, but is no longer detected (PREHEAT_PRES ERROR)",
    69: "Postheater was present, but is no longer detected (POSTHEAT_CONNECT ERROR)",
}

ERRORS = {
    **ERRORS_BASE,
    70: "Analog input 1 was present, but is no longer detected (ANALOG_1_PRES ERROR)",
    71: "Analog input 2 was present, but is no longer detected (ANALOG_2_PRES ERROR)",
    72: "Analog input 3 was present, but is no longer detected (ANALOG_3_PRES ERROR)",
    73: "Analog input 4 was present, but is no longer detected (ANALOG_4_PRES ERROR)",
    74: "ComfoHood was present, but is no longer detected (HOOD_CONNECT ERROR)",
    75: "ComfoCool was present, but is no longer detected (CCOOL_CONNECT ERROR)",
    76: "ComfoFond was present, but is no longer detected (GROUND_HEAT_CONNECT ERROR)",
    77: "The filters of the Ventilation Unit must be replaced now",
    78: "It is necessary to replace or clean the external filter",
    79: "Order new filters now, because the remaining filter life time is limited",
    80: "Service mode is active (SERVICE MODE)",
    81: "Preheater has no communication with the ComfoAir unit (PREHEAT ERROR , 1081)",
    82: "ComfoHood temperature error (HOOD_TEMP ERROR)",
    83: "Postheater temperature error (POSTHEAT_TEMP ERROR)",
    84: "Outdoor temperature of ComfoFond error (GROUND_HEAT_TEMP ERROR)",
    85: "Analog input 1 error (ANALOG_1_IN ERROR)",
    86: "Analog input 2 error (ANALOG_2_IN ERROR)",
    87: "Analog input 3 error (ANALOG_3_IN ERROR)",
    88: "Analog input 4 error (ANALOG_4_IN ERROR)",
    89: "Bypass is in manual mode",
    90: "ComfoCool is overheating",
    91: "ComfoCool compressor error (CCOOL_COMPRESSOR ERROR)",
    92: "ComfoCool room temperature sensor error (CCOOL_TEMP ERROR)",
    93: "ComfoCool condensor temperature sensor error (CCOOL_TEMP ERROR)",
    94: "ComfoCool supply air temperature sensor error (CCOOL_TEMP ERROR)",
    95: "ComfoHood temperature is too high (HOOD_TEMP ERROR)",
    96: "ComfoHood is activated",
    97: "QM_Constraint_min_ERR",  # Unknown error
    98: "H_21_qm_min_ERR",  # Unknown error
    99: "Configuration error",
    100: "Error analysis is in progress…",
    101: "ComfoNet Error",
    102: "The number of CO2 sensors has decreased – one or more sensors are no longer detected",
    103: "More than 8 sensors detected in a zone",
    104: "CO₂ Sensor C error",
}

ERRORS_140 = {
    **ERRORS_BASE,
    70: "ComfoHood was present, but is no longer detected (HOOD_CONNECT ERROR)",
    71: "ComfoCool was present, but is no longer detected (CCOOL_CONNECT ERROR)",
    72: "ComfoFond was present, but is no longer detected (GROUND_HEAT_CONNECT ERROR)",
    73: "The filters of the Ventilation Unit must be replaced now",
    74: "It is necessary to replace or clean the external filter",
    75: "Order new filters now, because the remaining filter life time is limited",
    76: "Service mode is active (SERVICE MODE)",
    77: "Preheater has no communication with the ComfoAir unit (PREHEAT ERROR , 1081)",
    78: "ComfoHood temperature error (HOOD_TEMP ERROR)",
    79: "Postheater temperature error (POSTHEAT_TEMP ERROR)",
    80: "Outdoor temperature of ComfoFond error (GROUND_HEAT_TEMP ERROR)",
    81: "Bypass is in manual mode",
    82: "ComfoCool is overheating",
    83: "ComfoCool compressor error (CCOOL_COMPRESSOR ERROR)",
    84: "ComfoCool room temperature sensor error (CCOOL_TEMP ERROR)",
    85: "ComfoCool condensor temperature sensor error (CCOOL_TEMP ERROR)",
    86: "ComfoCool supply air temperature sensor error (CCOOL_TEMP ERROR)",
}


class VentilationMode:
    """Enum for ventilation modes."""

    MANUAL = "manual"
    AUTO = "auto"


class VentilationSetting:
    """Enum for ventilation settings."""

    AUTO = "auto"
    ON = "on"
    OFF = "off"


class VentilationBalance:
    """Enum for ventilation balance."""

    BALANCE = "balance"
    SUPPLY_ONLY = "supply_only"
    EXHAUST_ONLY = "exhaust_only"


class VentilationTemperatureProfile:
    """Enum for ventilation temperature profiles."""

    WARM = "warm"
    NORMAL = "normal"
    COOL = "cool"


class VentilationSpeed:
    """Enum for ventilation speeds."""

    AWAY = "away"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
