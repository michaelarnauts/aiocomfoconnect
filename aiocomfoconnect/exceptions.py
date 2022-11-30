""" ComfoConnect Error definitions. """


class ComfoConnectError(Exception):
    """Base error for ComfoConnect"""

    def __init__(self, message):
        self.message = message


class ComfoConnectBadRequest(ComfoConnectError):
    """An error occured because the request was invalid."""

    pass


class ComfoConnectInternalError(ComfoConnectError):
    """An error occured because something went wrong inside the bridge."""

    pass


class ComfoConnectNotReachable(ComfoConnectError):
    """An error occured because the bridge could not reach the ventilation unit."""

    pass


class ComfoConnectOtherSession(ComfoConnectError):
    """An error occured because the bridge is already connected to a different device."""

    pass


class ComfoConnectNotAllowed(ComfoConnectError):
    """An error occured because you have not authenticated yet."""

    pass


class ComfoConnectNoResources(ComfoConnectError):
    pass


class ComfoConnectNotExist(ComfoConnectError):
    pass


class ComfoConnectRmiError(ComfoConnectError):
    pass
