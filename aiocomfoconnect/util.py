""" Helper methods. """
from __future__ import annotations


def bytestring(arr):
    """Join an array of bytes into a bytestring. Unlike `bytes()`, this method supports a mixed array with integers and bytes."""
    return b"".join([i if isinstance(i, bytes) else bytes([i]) for i in arr])


def bytearray_to_bits(arr):
    """Convert a bytearray to a list of set bits."""
    bits = []
    j = 0
    for byte in arr:
        for i in range(8):
            if byte & (1 << i):
                bits.append(j)
            j += 1
    return bits


def uint_to_bits(value):
    """Convert an unsigned integer to a list of set bits."""
    bits = []
    j = 0
    for i in range(64):
        if value & (1 << i):
            bits.append(j)
        j += 1
    return bits


def version_decode(version):
    """Decode the version number to a string."""
    v_1 = (version >> 30) & 3
    v_2 = (version >> 20) & 1023
    v_3 = (version >> 10) & 1023
    v_4 = version & 1023

    if v_1 == 0:
        v_1 = "U"
    elif v_1 == 1:
        v_1 = "D"
    elif v_1 == 2:
        v_1 = "P"
    elif v_1 == 3:
        v_1 = "R"

    return f"{v_1}{v_2}.{v_3}.{v_4}"


def pdo_to_can(pdo, node_id=1):
    """Convert a PDO-ID to a CAN-ID."""
    return ((pdo << 14) + 0x40 + node_id).to_bytes(4, byteorder="big").hex()


def can_to_pdo(can, node_id=1):
    """Convert a CAN-ID to a PDO-ID."""
    return (int(can, 16) - 0x40 - node_id) >> 14


def calculate_airflow_constraints(value):
    """Calculate the airflow constraints based on the bitshift value."""
    bits = uint_to_bits(value)
    if 45 not in bits:
        return None

    constraints = []
    if 2 in bits or 3 in bits:
        constraints.append("Resistance")
    if 4 in bits:
        constraints.append("PreheaterNegative")
    if 5 in bits or 7 in bits:
        constraints.append("NoiseGuard")
    if 6 in bits or 8 in bits:
        constraints.append("ResistanceGuard")
    if 9 in bits:
        constraints.append("FrostProtection")
    if 10 in bits:
        constraints.append("Bypass")
    if 12 in bits:
        constraints.append("AnalogInput1")
    if 13 in bits:
        constraints.append("AnalogInput2")
    if 14 in bits:
        constraints.append("AnalogInput3")
    if 15 in bits:
        constraints.append("AnalogInput4")
    if 16 in bits:
        constraints.append("Hood")
    if 18 in bits:
        constraints.append("AnalogPreset")
    if 19 in bits:
        constraints.append("ComfoCool")
    if 22 in bits:
        constraints.append("PreheaterPositive")
    if 23 in bits:
        constraints.append("RFSensorFlowPreset")
    if 24 in bits:
        constraints.append("RFSensorFlowProportional")
    if 25 in bits:
        constraints.append("TemperatureComfort")
    if 26 in bits:
        constraints.append("HumidityComfort")
    if 27 in bits:
        constraints.append("HumidityProtection")
    if 47 in bits:
        constraints.append("CO2ZoneX1")
    if 48 in bits:
        constraints.append("CO2ZoneX2")
    if 49 in bits:
        constraints.append("CO2ZoneX3")
    if 50 in bits:
        constraints.append("CO2ZoneX4")
    if 51 in bits:
        constraints.append("CO2ZoneX5")
    if 52 in bits:
        constraints.append("CO2ZoneX6")
    if 53 in bits:
        constraints.append("CO2ZoneX7")
    if 54 in bits:
        constraints.append("CO2ZoneX8")

    return constraints
