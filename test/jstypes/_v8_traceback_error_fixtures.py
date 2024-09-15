from __future__ import annotations

import sys
from traceback import TracebackException
from typing import Callable
from typing_extensions import Never

if sys.version_info < (3, 11):
    from exceptiongroup import ExceptionGroup


class ErrorScenario:
    """
    Functions that raise errors with various attached context/exception groups.

    Used to generate well-known exceptions to test traceback formatting
    behaviour.
    """

    def raise_simple(self) -> Never:
        self.failing_operation()

    def raise_group(self) -> Never:
        try:
            self.failing_operation()
        except Exception as e:
            fail1 = e

        try:
            self.failing_operation2()
        except Exception as e:
            fail2 = e

        raise ExceptionGroup("Everything went wrong", [fail1, fail2])

    def raise_context(self) -> Never:
        try:
            self.failing_operation()
        except Exception as e:
            e / 0  # type: ignore[operator]
            raise AssertionError("unreachable") from e

    def raise_context_group(self) -> Never:
        try:
            self.raise_group()
        except Exception as e:
            e / 0  # type: ignore[operator]
            raise AssertionError("unreachable") from e

    def raise_group_with_context(self) -> Never:
        try:
            self.failing_operation_with_context()
        except Exception as e:
            fail1 = e

        try:
            self.failing_operation2()
        except Exception as e:
            fail2 = e

        raise ExceptionGroup("Everything went wrong", [fail1, fail2])

    def raise_sub_group_with_context(self) -> Never:
        try:
            self.raise_group_with_context()
        except Exception as e:
            fail1 = e

        try:
            self.raise_group()
        except Exception as e:
            fail2 = e

        raise ExceptionGroup("This is fine", [fail1, fail2])

    def failing_operation(self) -> Never:
        if True:
            raise ValueError("Unable to do the thing")

    def failing_operation2(self) -> Never:
        if True:
            raise TypeError("Expected an Apple but received an Orange")

    def failing_operation_with_context(self) -> Never:
        try:
            self.failing_operation()
        except Exception as e:
            e.missing_attribute.foo()  # type: ignore[attr-defined]
            raise AssertionError("unreachable") from e


def call_and_capture_tbe(fn: Callable[[], Never]) -> TracebackException:
    try:
        fn()
    except Exception as e:
        return TracebackException.from_exception(e)
    raise AssertionError("fn did not raise")
