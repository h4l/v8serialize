from __future__ import annotations

from collections.abc import Iterable, Sequence
from itertools import zip_longest
from traceback import FrameSummary, TracebackException
from typing import Generator, cast


def format_exception_for_v8(
    tbe: TracebackException, group_path: Sequence[int] = ()
) -> Generator[str]:
    r"""Render a Python exception in the style of a V8 Error stack trace.

    Returns an iterable of strings ending with `"\n"`. (Join the lines to get a
    complete stack trace.)

    This aims to follow the layout described in https://v8.dev/docs/stack-trace-api

    V8 stack traces are in the reverse order of Python — most recent call first.
    They also omit details of of the the source code line that each stack entry
    corresponds to. For example, in V8 format:

    ```
    ValueError: Unable to do the thing
        at failing_operation (/…/v8serialize/test/jstypes/_v8_traceback_error_fixtures.py:66:12)
        at raise_simple (/…/v8serialize/test/jstypes/_v8_traceback_error_fixtures.py:11:8)
        at call_and_capture_tbe (/…/v8serialize/test/jstypes/_v8_traceback_error_fixtures.py:82:8)
    ```

    vs Python:

    ```
    Traceback (most recent call last):
    File "/…/v8serialize/test/jstypes/_v8_traceback_error_fixtures.py", line 82, in call_and_capture_tbe
        fn()
    File "/…/v8serialize/test/jstypes/_v8_traceback_error_fixtures.py", line 11, in raise_simple
        self.failing_operation()
    File "/…/v8serialize/test/jstypes/_v8_traceback_error_fixtures.py", line 66, in failing_operation
        raise ValueError("Unable to do the thing")
    ValueError: Unable to do the thing
    ```

    V8's JavaScript Errors don't support the __context__ feature of Python
    exceptions, and V8 serialization doesn't support JavaScript's
    AggregateError, but it does support linking exceptions via `cause`. With this
    in mind, this format encodes details of context exceptions and
    sub-exceptions of exception groups in the string of the root exception. It
    does not include cause exceptions, because causes can be represented
    natively as `cause`.
    """  # noqa: E501
    yield from format_v8_stack(tbe, group_path=group_path)

    for related in walk_related(tbe):
        yield from [
            "\n",
            "The above exception occurred while handling another exception:\n",
            "\n",
        ]
        yield from format_v8_stack(related, group_path=())


def walk_related(tbe: TracebackException) -> Generator[TracebackException]:
    while tbe.__context__ and not tbe.__suppress_context__:
        yield tbe.__context__
        tbe = tbe.__context__


def format_v8_stack(
    tbe: TracebackException, *, group_path: Sequence[int]
) -> Generator[str]:
    # e.g. "ValueError: foo must be positive"
    yield from tbe.format_exception_only()

    if tbe.stack:
        # e.g. "    at main (/foo/bar.py:8:4)"
        yield from (format_v8_frame(fs) for fs in reversed(tbe.stack))

    sub_exceptions: list[TracebackException] | None = getattr(
        tbe, "exceptions", None
    )  # 3.11+
    if sub_exceptions:
        for i, sub_tbe in enumerate(
            cast(Sequence[TracebackException], sub_exceptions), start=1
        ):
            sub_group_path = [*group_path, i]
            yield "\n"
            prefixes = [f"  ↳ {format_group_path(sub_group_path)}: ", "    "]
            yield from prefix_lines(
                format_exception_for_v8(sub_tbe, group_path=sub_group_path), prefixes
            )


def format_group_path(group_path: Sequence[int]) -> str:
    return ".".join(map(str, group_path))


def prefix_lines(lines: Iterable[str], prefixes: Iterable[str]) -> Generator[str]:
    last_prefix = ""
    for line, prefix in zip_longest(lines, prefixes):
        if line is None:
            return
        if prefix is None:
            prefix = last_prefix
        else:
            last_prefix = prefix
        result = f"{prefix}{line}"
        yield result.lstrip(" ") if result.isspace() else result


def format_v8_frame(fs: FrameSummary) -> str:
    return f"    at {fs.name} {format_v8_frame_location(fs)}\n"


def format_v8_frame_location(fs: FrameSummary) -> str:
    if fs.filename is None and fs.lineno is None and fs.colno is None:
        return "(unknown location)"

    filename = sub_none(fs.filename, "<unknown>")
    lineno = sub_none(fs.lineno, "<unknown>")
    # colno available from 3.11
    colno = sub_none(getattr(fs, "colno", None), "<unknown>")

    return f"({filename}:{lineno}:{colno})"


def sub_none(value: object, none_substitute: str) -> str:
    return none_substitute if value is None else str(value)
