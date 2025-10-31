"""Tests for utility helpers."""

from aiocomfoconnect.const import PdoType
from aiocomfoconnect.util import encode_pdo_value


def test_encode_pdo_value_bool():
    """Boolean values should round-trip to single-byte payloads."""
    assert encode_pdo_value(True, PdoType.TYPE_CN_BOOL) == b"\x01"
    assert encode_pdo_value(False, PdoType.TYPE_CN_BOOL) == b"\x00"
    assert encode_pdo_value(0, PdoType.TYPE_CN_BOOL) == b"\x00"
    assert encode_pdo_value(5, PdoType.TYPE_CN_BOOL) == b"\x01"
