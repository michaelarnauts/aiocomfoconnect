""" Error definitions """

from __future__ import annotations


class AioComfoConnectError(Exception):
    """Base class for all errors raised by aiocomfoconnect."""


def _describe(message) -> str:
    """Build a readable description of an error reply from the bridge."""
    cmd = getattr(message, "cmd", None)
    if cmd is None:
        return str(message)

    def enum_name(field: str) -> str:
        value = getattr(cmd, field)
        enum_value = cmd.DESCRIPTOR.fields_by_name[field].enum_type.values_by_number.get(value)
        return enum_value.name if enum_value else str(value)

    description = f"Bridge replied {enum_name('result')} to {enum_name('type')} (reference {cmd.reference})"
    if cmd.resultDescription:
        description += f": {cmd.resultDescription}"
    return description


class ComfoConnectError(AioComfoConnectError):
    """Base error for ComfoConnect"""

    def __init__(self, message):
        super().__init__(_describe(message))
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


class AioComfoConnectNotConnected(AioComfoConnectError):
    """An error occurred because the bridge is not connected."""


class AioComfoConnectSessionClosed(AioComfoConnectNotConnected):
    """The bridge closed the session, for example because another app took it over."""


class AioComfoConnectTimeout(AioComfoConnectError):
    """An error occurred because the bridge didn't reply in time."""


class AioComfoConnectNotReachable(AioComfoConnectError):
    """An error occurred because the bridge could not be reached, for example when it moved to another address."""


class BridgeNotFoundException(AioComfoConnectError):
    """Exception raised when no bridge is found."""


class VentilationUnitNotFoundException(AioComfoConnectError):
    """Exception raised when the bridge didn't announce a ventilation unit on the ComfoNet bus."""


class ComfoClimeNotFoundException(AioComfoConnectError):
    """Exception raised when the bridge didn't announce a ComfoClime on the ComfoNet bus."""


class SelfDeregistrationError(AioComfoConnectError):
    """Exception raised when trying to deregister self."""
