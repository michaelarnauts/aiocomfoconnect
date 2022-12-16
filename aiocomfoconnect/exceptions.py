""" ComfoConnect Error definitions. """


class ComfoConnectError(Exception):
    """Base error for ComfoConnect"""

    def __init__(self, message):
        self.message = message


class ComfoConnectBadRequest(ComfoConnectError):
    """Something was wrong with the request."""

    pass


class ComfoConnectInternalError(ComfoConnectError):
    """The request was ok, but the handling of the request failed."""

    pass


class ComfoConnectNotReachable(ComfoConnectError):
    """The backend cannot route the request."""

    pass


class ComfoConnectOtherSession(ComfoConnectError):
    """The gateway already has an active session with another client."""

    pass


class ComfoConnectNotAllowed(ComfoConnectError):
    """Request is not allowed."""

    pass


class ComfoConnectNoResources(ComfoConnectError):
    """Not enough resources, e.g., memory, to complete request"""

    pass


class ComfoConnectNotExist(ComfoConnectError):
    """ComfoNet node or property does not exist."""

    pass


class ComfoConnectRmiError(ComfoConnectError):
    """The RMI failed, the message contains the error response."""

    pass


class AioComfoConnectNotConnected(Exception):
    """An error occured because the bridge is not connected."""

    pass
