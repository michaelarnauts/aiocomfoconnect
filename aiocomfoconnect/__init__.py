""" aiocomfoconnect library """

from .bridge import Bridge  # noqa
from .comfoconnect import ComfoConnect  # noqa
from .discovery import discover_bridges  # noqa

DEFAULT_UUID = "00000000000000000000000000000001"
DEFAULT_PIN = 0
DEFAULT_NAME = "aiocomfoconnect"
