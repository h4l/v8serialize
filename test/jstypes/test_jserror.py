from v8serialize._values import AnyJSError
from v8serialize.constants import JSErrorName
from v8serialize.jstypes.jserror import JSError, JSErrorData


def test_JSErrorData_types() -> None:
    # Verify that JSErrorData satisfies the AnyJSError protocol
    any_error: AnyJSError = JSErrorData(
        name=JSErrorName.Error, message="Oops", stack="..."
    )
    assert any_error.name == JSErrorName.Error
    assert any_error.message == "Oops"
    assert any_error.stack == "..."


def test_JSError_types() -> None:
    # We don't inherit AnyJSError protocol directly because its @properties
    # affect the subclass, but JSError must satisfy its type signature.
    any_error: AnyJSError = JSError("msg")
    # JSError is a virtual subclass of JSErrorData, this is how the encoder
    # recognises it as a AnyJSError implementation.
    assert isinstance(any_error, JSErrorData)


def test_JSError_init() -> None:
    jserror = JSError("msg", name=JSErrorName.UriError, stack="...", cause={})
    assert jserror.message == "msg"
    assert jserror.name == "UriError"
    assert jserror.stack == "..."
    assert jserror.cause == {}
