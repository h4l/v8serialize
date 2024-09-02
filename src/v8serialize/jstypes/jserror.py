from __future__ import annotations

from abc import ABC
from dataclasses import dataclass, field
from traceback import TracebackException
from typing import TYPE_CHECKING, Final

from v8serialize._pycompat.dataclasses import slots_if310
from v8serialize._recursive_eq import recursive_eq
from v8serialize._values import AnyJSError, JSErrorBuilder
from v8serialize.constants import JSErrorName
from v8serialize.errors import V8CodecError
from v8serialize.jstypes import _repr
from v8serialize.jstypes._v8traceback import (
    format_exception_for_v8 as format_exception_for_v8,  # re-export
)

if TYPE_CHECKING:
    from typing_extensions import Self


# We define this dataclass separately from AnyJSError, because AnyJSError's
# @property fields seem to confuse @dataclass — it sets property objects as
# instance field values instead of str.
@recursive_eq
@dataclass(order=True, **slots_if310())
class _JSErrorData:
    message: str | None = field(default=None)
    name: str = field(default=JSErrorName.Error, kw_only=True)
    stack: str | None = field(default=None, kw_only=True)
    cause: object | None = field(default=None, kw_only=True)


class JSErrorData(_JSErrorData, AnyJSError, ABC):
    """A minimal representation of JavaScript Error data that isn't a Python
    Exception."""

    @classmethod
    def from_exception(cls, exc: BaseException) -> Self:
        return cls.from_traceback_exception(TracebackException.from_exception(exc))

    @classmethod
    def from_traceback_exception(cls, tbe: TracebackException) -> Self:
        message = _get_message(tbe)
        stack = "".join(format_exception_for_v8(tbe)).rstrip()

        # TODO: TracebackException cuts cycles in __cause__, but in principle we
        #   can include cycles in JSError's cause. Should we?
        cause = None
        if tbe.__cause__:
            cause = cls.from_traceback_exception(tbe.__cause__)

        return cls(
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


@recursive_eq
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

    def __eq__(self, other: object) -> bool:
        if self is other:
            return True
        if (
            isinstance(other, BaseException)
            and self.__traceback__ != other.__traceback__
        ):
            return False
        if isinstance(other, JSErrorData):
            return (self.name, self.message, self.stack, self.cause) == (
                other.name,
                other.message,
                other.stack,
                other.cause,
            )
        return NotImplemented


if TYPE_CHECKING:
    # type assertion
    _js_error_builder: Final[JSErrorBuilder[JSError]] = JSError.builder
    _js_error_data_builder: Final[JSErrorBuilder[JSErrorData]] = JSErrorData.builder
