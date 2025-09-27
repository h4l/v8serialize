from __future__ import annotations

from abc import ABC
from dataclasses import dataclass, field
from traceback import TracebackException
from typing import TYPE_CHECKING, Final

from v8serialize._errors import V8SerializeError
from v8serialize._recursive_eq import recursive_eq
from v8serialize._values import AnyJSError, JSErrorBuilder
from v8serialize.constants import JSErrorName
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
@dataclass(order=True, slots=True, init=False)
class _JSErrorData:
    message: str | None
    name: str
    stack: str | None
    cause: object | None

    # kw_only field option is not available before 3.10, so we need to define
    # init manually to match JSError.__init__
    def __init__(
        self,
        message: str | None = None,
        *,
        name: str = JSErrorName.Error,
        stack: str | None = None,
        cause: object | None = None,
    ) -> None:
        self.message = message
        self.name = name
        self.stack = stack
        self.cause = cause


class JSErrorData(_JSErrorData, AnyJSError, ABC):
    """
    A minimal representation of a JavaScript `Error`.

    This type holds just the JavaScript `Error` fields that are stored in the V8
    Serialization format. It doesn't extend Python's Exception type. Use this to
    represent JavaScript Error values that don't need to be treated like Python
    Exceptions.

    [`JSErrorName`]: `v8serialize.JSErrorName`

    Parameters
    ----------
    message
        A description of the error.
    name
        The name of the error type. Can be anything, but values not in
        [`JSErrorName`] are equivalent to using `"Error"`.
    stack
        The stack trace detailing where the error happened.
    cause:
        Any object or value that caused this error.
    """

    @classmethod
    def from_exception(cls, exc: BaseException) -> Self:
        """Create `JSErrorData` that reproduces the details of a Python Exception."""
        return cls.from_traceback_exception(TracebackException.from_exception(exc))

    @classmethod
    def from_traceback_exception(cls, tbe: TracebackException) -> Self:
        """Create `JSErrorData` containing details from a `TracebackException`."""
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
        """
        Create a `JSErrorData` by copying another, satisfying [`JSErrorBuilder`].

        This is a [`JSErrorBuilder`] function to configure [`TagReader`] to
        build `JSErrorData`s.

        [`JSErrorBuilder`]: `v8serialize.decode.JSErrorBuilder`
        """
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
class JSError(AnyJSError, V8SerializeError):
    """A Python Exception that represents a JavaScript Error.

    This is intended to be used to handle JavaScript errors on the Python side.
    To send Python errors to JavaScript, use JSErrorData.from_exception() to
    format a Python Exception like a JavaScript Error. (This happens
    automatically when serializing Python Exceptions.)
    """

    name: str | JSErrorName
    """The JavaScript Error's name.

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
        # Serialized errors can have message, but V8SerializeError expects one
        if message is None:
            message = ""
        super(JSError, self).__init__(message)
        self.name = name
        self.__message = message
        self.stack = stack
        self.cause = cause

    @property
    def message(self) -> str:
        """The JavaScript Error's message."""
        return self.__message

    @message.setter
    def message(self, message: str | None) -> None:
        self.__message = message or ""

    @classmethod
    def from_js_error(cls, js_error: AnyJSError) -> Self:
        """Create a `JSError` by copying fields from another JSError-like object."""
        return cls(
            name=js_error.name,
            message=js_error.message,
            stack=js_error.stack,
            cause=js_error.cause,
        )

    @classmethod
    def builder(cls, initial_js_error: AnyJSError, /) -> tuple[Self, Self]:
        """
        Create a `JSError` by copying another, satisfying [`JSErrorBuilder`].

        This is a [`JSErrorBuilder`] function to configure [`TagReader`] to
        build `JSError`s.

        [`TagReader`] has `js_error_builder` option that this function can be
        passed to to have it create `JSError` objects when deserializing
        JavaScript Errors.

        [`JSErrorBuilder`]: `v8serialize.decode.JSErrorBuilder`
        [`TagReader`]: `v8serialize.decode.TagReader`
        """
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
