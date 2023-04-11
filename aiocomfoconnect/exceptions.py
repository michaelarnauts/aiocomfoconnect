""" Error definitions """
from __future__ import annotations


class ComfoConnectError(Exception):
    """Base error for ComfoConnect"""

    def __init__(self, message):
        self.message = message


class ComfoConnectBadRequest(ComfoConnectError):
    """Something was wrong with the request."""


class ComfoConnectInternalError(ComfoConnectError):
    """The request was ok, but the handling of the request failed."""


class ComfoConnectNotReachable(ComfoConnectError):
    """The backend cannot route the request."""


class ComfoConnectOtherSession(ComfoConnectError):
    """The gateway already has an active session with another client."""


class ComfoConnectNotAllowed(ComfoConnectError):
    """Request is not allowed."""


class ComfoConnectNoResources(ComfoConnectError):
    """Not enough resources, e.g., memory, to complete request"""


class ComfoConnectNotExist(ComfoConnectError):
    """ComfoNet node or property does not exist."""


class ComfoConnectRmiError(ComfoConnectError):
    """The RMI failed, the message contains the error response."""


class AioComfoConnectNotConnected(Exception):
    """An error occurred because the bridge is not connected."""


class AioComfoConnectTimeout(Exception):
    """An error occurred because the bridge didn't reply in time."""
