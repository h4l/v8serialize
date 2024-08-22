from abc import ABC
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, overload

from v8serialize._values import AnyJSError
from v8serialize.constants import JSErrorName
from v8serialize.errors import V8CodecError


# We define this dataclass separately from AnyJSError, because AnyJSError's
# @property fields seem to confuse @dataclass — it sets property objects as
# instance field values instead of str.
@dataclass(slots=True, order=True)
class _JSErrorData:
    name: str = field(default=JSErrorName.Error)
    message: str | None = field(default=None)
    stack: str | None = field(default=None)
    cause: object | None = field(default=None)


class JSErrorData(_JSErrorData, AnyJSError, ABC):
    """A minimal representation of JavaScript Error data that isn't a Python
    Exception."""

    if TYPE_CHECKING:
        # This overload satisfies JSErrorSettableCauseConstructor
        @overload
        def __init__(
            self, name: JSErrorName, message: str | None, stack: str | None
        ) -> None: ...

        @overload
        def __init__(
            self,
            name: str = JSErrorName.Error,
            message: str | None = None,
            stack: str | None = None,
            cause: object | None = None,
        ) -> None: ...

        def __init__(
            self,
            name: str = JSErrorName.Error,
            message: str | None = None,
            stack: str | None = None,
            cause: object | None = None,
        ) -> None: ...


@JSErrorData.register
@dataclass(init=False)
class JSError(V8CodecError):
    """A JavaScript Error deserialized from V8 data.

    This is intended to be used to handle JavaScript errors on the Python side.
    To send Python errors to JavaScript, use JSErrorData.from_exception() to
    format a Python Exception like a JavaScript Error. (This happens
    automatically when serializing Python Exceptions.)
    """

    name: str | JSErrorName
    """The JavaScript error name.

    Can be any string, but unrecognised names become "Error" when serialized, so
    deserialized values will always be one of the JSErrorName constants.
    """
    stack: str | None
    """The stack trace showing details of the Error and the calls that lead up
    to the error."""
    cause: object | None
    """Another error (or arbitrary object) that this error was caused by."""

    def __init__(
        self,
        message: str | None,
        *,
        name: str | JSErrorName = JSErrorName.Error,
        stack: str | None = None,
        cause: object | None = None,
    ) -> None:
        # Serialized errors can have message, but V8CodecError expects one
        if message is None:
            message = ""
        super(JSError, self).__init__(message)
        self.name = name
        self.stack = stack
        self.cause = cause
