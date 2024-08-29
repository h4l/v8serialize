from __future__ import annotations

from abc import ABC
from dataclasses import dataclass, field
from traceback import TracebackException
from typing import TYPE_CHECKING, Final, Self

from v8serialize._values import AnyJSError, JSErrorBuilder
from v8serialize.constants import JSErrorName
from v8serialize.errors import V8CodecError
from v8serialize.jstypes import _repr
from v8serialize.jstypes._v8traceback import (
    format_exception_for_v8 as format_exception_for_v8,  # re-export
)


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

        def __init__(
            self,
            name: str = JSErrorName.Error,
            message: str | None = None,
            stack: str | None = None,
            cause: object | None = None,
        ) -> None: ...

    @classmethod
    def from_exception(cls, exc: BaseException) -> JSErrorData:
        return cls.from_traceback_exception(TracebackException.from_exception(exc))

    @classmethod
    def from_traceback_exception(cls, tbe: TracebackException) -> JSErrorData:
        message = _get_message(tbe)
        stack = "".join(format_exception_for_v8(tbe)).rstrip()

        # TODO: TracebackException cuts cycles in __cause__, but in principle we
        #   can include cycles in JSError's cause. Should we?
        cause = None
        if tbe.__cause__:
            cause = cls.from_traceback_exception(tbe.__cause__)

        return JSErrorData(
            # We always use just Error as the name, as Python errors can't
            # really be considered to be equivalent to JS Error types. The
            # message property we set will contain the name of the Python error
            # in most cases, e.g. "ValueError: too low".
            name=JSErrorName.Error,
            message=message,
            stack=stack,
            cause=cause,
        )

    @classmethod
    def builder(cls, initial_js_error: AnyJSError, /) -> tuple[Self, Self]:
        js_error = cls(
            name=initial_js_error.name,
            message=initial_js_error.message,
            stack=initial_js_error.stack,
            cause=initial_js_error.cause,
        )
        return js_error, js_error


def _get_message(tbe: TracebackException) -> str | None:
    # This includes the exception type, like "ValueError: too low". That'
    # probably a good thing for JavaScript because we can't communicate the
    # error name via the name property, because it has a fixed set of values.
    # The message property is not displayed by V8 runtimes I've tried, they just
    # show the stack string.
    return next((ln.rstrip() for ln in tbe.format_exception_only()), None)


@JSErrorData.register
@dataclass(init=False)
class JSError(AnyJSError, V8CodecError):
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
    __message: str = field(repr=False)
    stack: str | None
    """The stack trace showing details of the Error and the calls that lead up
    to the error."""
    cause: object | None
    """Another error (or arbitrary object) that this error was caused by."""

    def __init__(
        self,
        message: str | None = None,
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
        self.__message = message
        self.stack = stack
        self.cause = cause

    @property  # type: ignore[override]
    def message(self) -> str:
        return self.__message

    @message.setter
    def message(self, message: str | None) -> None:
        self.__message = message or ""

    @classmethod
    def from_js_error(cls, js_error: AnyJSError) -> Self:
        return cls(
            name=js_error.name,
            message=js_error.message,
            stack=js_error.stack,
            cause=js_error.cause,
        )

    @classmethod
    def builder(cls, initial_js_error: AnyJSError, /) -> tuple[Self, Self]:
        js_error = cls.from_js_error(initial_js_error)
        return js_error, js_error

    def __repr__(self) -> str:
        return _repr.js_repr(self)


if TYPE_CHECKING:
    # type assertion
    _js_error_builder: Final[JSErrorBuilder[JSError]] = JSError.builder
    _js_error_data_builder: Final[JSErrorBuilder[JSErrorData]] = JSErrorData.builder
