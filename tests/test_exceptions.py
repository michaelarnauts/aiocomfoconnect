"""Tests for the exception hierarchy."""

import inspect

import pytest

from aiocomfoconnect import exceptions
from aiocomfoconnect.bridge import Message
from aiocomfoconnect.exceptions import (
    AioComfoConnectError,
    AioComfoConnectNotConnected,
    AioComfoConnectSessionClosed,
    ComfoClimeNotFoundException,
    ComfoConnectError,
    ComfoConnectNotAllowed,
    ComfoConnectRmiError,
    NodeNotFoundException,
    SelfDeregistrationError,
    VentilationUnitNotFoundException,
)
from aiocomfoconnect.protobuf import zehnder_pb2

LOCAL_UUID = "00000000000000000000000000000001"

EXCEPTION_CLASSES = [cls for _, cls in inspect.getmembers(exceptions, inspect.isclass) if issubclass(cls, BaseException) and cls.__module__ == exceptions.__name__]


@pytest.mark.parametrize("cls", EXCEPTION_CLASSES, ids=lambda cls: cls.__name__)
def test_every_exception_is_an_aiocomfoconnect_error(cls):
    """Every exception of the library can be caught with AioComfoConnectError."""
    assert issubclass(cls, AioComfoConnectError)


def test_existing_parents_are_kept():
    """The base class is added without breaking existing except clauses."""
    assert issubclass(AioComfoConnectSessionClosed, AioComfoConnectNotConnected)
    assert issubclass(ComfoConnectNotAllowed, ComfoConnectError)


@pytest.mark.parametrize("cls", [VentilationUnitNotFoundException, ComfoClimeNotFoundException])
def test_node_not_found_exceptions(cls):
    """A missing node of any kind can be caught with NodeNotFoundException."""
    assert issubclass(cls, NodeNotFoundException)
    assert issubclass(cls, AioComfoConnectError)


def test_self_deregistration_error_importable_from_bridge():
    """SelfDeregistrationError moved to exceptions.py, but can still be imported from bridge.py."""
    from aiocomfoconnect.bridge import SelfDeregistrationError as FromBridge  # pylint: disable=import-outside-toplevel

    assert FromBridge is SelfDeregistrationError


def test_comfoconnect_error_str_with_text():
    """A ComfoConnectError created with a string uses it as its message."""
    exc = ComfoConnectNotAllowed("not registered")
    assert str(exc) == "not registered"
    assert exc.message == "not registered"


def test_comfoconnect_error_str_with_bridge_reply():
    """A ComfoConnectError created from a bridge reply has a readable message and keeps the reply."""
    cmd = zehnder_pb2.GatewayOperation()
    cmd.type = zehnder_pb2.GatewayOperation.CnRmiRequestType
    cmd.reference = 42
    cmd.result = zehnder_pb2.GatewayOperation.RMI_ERROR
    cmd.resultDescription = "something failed"
    message = Message(cmd, zehnder_pb2.CnRmiResponse(), LOCAL_UUID, LOCAL_UUID)

    exc = ComfoConnectRmiError(message)

    assert str(exc) == "RMI_ERROR: something failed (reference 42)"
    assert exc.message is message
    assert exc.message.cmd.reference == 42


def test_comfoconnect_error_str_without_description():
    """Without a result description, the result and the reference are used."""
    cmd = zehnder_pb2.GatewayOperation()
    cmd.type = zehnder_pb2.GatewayOperation.StartSessionRequestType
    cmd.reference = 1
    cmd.result = zehnder_pb2.GatewayOperation.NOT_ALLOWED
    message = Message(cmd, zehnder_pb2.StartSessionConfirm(), LOCAL_UUID, LOCAL_UUID)

    assert str(ComfoConnectNotAllowed(message)) == "NOT_ALLOWED (reference 1)"
