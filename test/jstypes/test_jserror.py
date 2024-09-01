from __future__ import annotations

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
    assert jserror.name == JSErrorName.UriError
    assert jserror.stack == "..."
    assert jserror.cause == {}


def test_JSError_builder() -> None:
    jserror, state = JSError.builder(
        JSErrorData(message="msg", name=JSErrorName.UriError, stack="...", cause={})
    )
    assert jserror is state
    state.name = JSErrorName.EvalError
    state.message = "example"
    state.cause = 1
    state.stack = "foo"
    assert jserror == JSError(
        "example", name=JSErrorName.EvalError, stack="foo", cause=1
    )


def test_JSError_repr() -> None:
    jserror = JSError("msg", name=JSErrorName.UriError, stack="Boom", cause={})
    assert repr(jserror) == (
        "JSError('msg', name=<JSErrorName.UriError: 'UriError'>, stack='Boom', "
        "cause={})"
    )

    # repr is recursion safe with cycles in cause
    jserror.cause = jserror
    assert (
        repr(jserror)
        == """\
JSError('msg', name=<JSErrorName.UriError: 'UriError'>, stack='Boom', cause=\
JSError('msg', name=<JSErrorName.UriError: 'UriError'>, stack='Boom', cause=...))\
"""
    )


def test_JSError__eq() -> None:
    e1 = JSError("foo")
    e2 = JSError("foo")

    # JSError are equal as normal (unless they have different tracebacks)
    assert e1 == e2

    # recursive cause does not blow up == check
    e1.cause = e1
    e2.cause = e2
    assert e1 == e2

    e1.cause = [e1]
    e2.cause = [e2]
    assert e1 == e2

    # JSErrors which have been raised have tracebacks, which are not equal for
    # distinct raises.
    for e in [e1, e2]:
        try:
            raise e
        except JSError:
            pass

    assert e1 != e2


def test_JSErrorData__eq() -> None:
    # Unlike JSError, JSErrorData objects are equal by value
    e1 = JSErrorData(name=JSErrorName.EvalError, message="Hi", stack="Xyz", cause=42)
    e2 = JSErrorData(name=JSErrorName.EvalError, message="Hi", stack="Xyz", cause=42)

    assert e1 == e2

    # Errors with recursive causes can be eq
    e1.cause = JSErrorData(cause=e1)
    e2.cause = JSErrorData(cause=e2)

    assert e1 == e2

    # Or not eq
    e2.cause.message = "Blah"

    assert e1 != e2
