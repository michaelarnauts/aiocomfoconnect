"""Tests for utility helpers."""

import pytest

from aiocomfoconnect.const import PdoType
from aiocomfoconnect.util import encode_pdo_value


def test_pdo_type_ids():
    """The type ids are the ones the bridge uses: 0 to 11, in the order of the type table in PROTOCOL-PDO.md."""
    names = ["BOOL", "UINT8", "UINT16", "UINT32", "UINT64", "INT8", "INT16", "INT32", "INT64", "STRING", "TIME", "VERSION"]
    assert [getattr(PdoType, f"TYPE_CN_{name}") for name in names] == list(range(12))


def test_encode_pdo_value_bool():
    """Boolean values should round-trip to single-byte payloads."""
    assert encode_pdo_value(True, PdoType.TYPE_CN_BOOL) == b"\x01"
    assert encode_pdo_value(False, PdoType.TYPE_CN_BOOL) == b"\x00"
    assert encode_pdo_value(0, PdoType.TYPE_CN_BOOL) == b"\x00"
    assert encode_pdo_value(5, PdoType.TYPE_CN_BOOL) == b"\x01"


@pytest.mark.parametrize(
    "pdo_type,value,expected",
    [
        (PdoType.TYPE_CN_UINT8, 0, b"\x00"),
        (PdoType.TYPE_CN_UINT8, 255, b"\xff"),
        (PdoType.TYPE_CN_UINT16, 65535, b"\xff\xff"),
        (PdoType.TYPE_CN_UINT16, 258, b"\x02\x01"),
        (PdoType.TYPE_CN_UINT32, 4294967295, b"\xff\xff\xff\xff"),
        (PdoType.TYPE_CN_UINT64, 2**64 - 1, b"\xff" * 8),
        (PdoType.TYPE_CN_INT8, -128, b"\x80"),
        (PdoType.TYPE_CN_INT8, 127, b"\x7f"),
        (PdoType.TYPE_CN_INT16, -32768, b"\x00\x80"),
        (PdoType.TYPE_CN_INT16, -20, b"\xec\xff"),
        (PdoType.TYPE_CN_INT32, -2, b"\xfe\xff\xff\xff"),
        (PdoType.TYPE_CN_INT64, -1, b"\xff" * 8),
        (PdoType.TYPE_CN_INT64, 2**63 - 1, b"\xff" * 7 + b"\x7f"),
    ],
)
def test_encode_pdo_value_numeric(pdo_type, value, expected):
    """Numeric values are encoded little-endian with the size and signedness of their type."""
    assert encode_pdo_value(value, pdo_type) == expected


@pytest.mark.parametrize(
    "pdo_type,value",
    [
        (PdoType.TYPE_CN_UINT8, 256),
        (PdoType.TYPE_CN_UINT8, -1),
        (PdoType.TYPE_CN_UINT16, 65536),
        (PdoType.TYPE_CN_UINT32, 2**32),
        (PdoType.TYPE_CN_UINT64, -1),
        (PdoType.TYPE_CN_INT8, 128),
        (PdoType.TYPE_CN_INT16, -32769),
        (PdoType.TYPE_CN_INT32, 2**31),
        (PdoType.TYPE_CN_INT64, 2**63),
    ],
)
def test_encode_pdo_value_out_of_range(pdo_type, value):
    """A value that doesn't fit its type raises."""
    with pytest.raises(OverflowError):
        encode_pdo_value(value, pdo_type)


@pytest.mark.parametrize("pdo_type", [PdoType.TYPE_CN_STRING, PdoType.TYPE_CN_TIME, PdoType.TYPE_CN_VERSION, 0x0C, None])
def test_encode_pdo_value_unsupported(pdo_type):
    """Types that aren't numeric or bool can't be encoded."""
    with pytest.raises(ValueError, match="not supported"):
        encode_pdo_value(1, pdo_type)
