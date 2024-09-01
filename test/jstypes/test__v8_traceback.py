from __future__ import annotations

from test.jstypes._v8_traceback_error_fixtures import (
    ErrorScenario,
    call_and_capture_tbe,
)
from typing import Callable, Never, cast

import pytest
from pytest_insta import SnapshotFixture

from v8serialize.jstypes._v8traceback import format_exception_for_v8

FmtExc = Callable[[Callable[[], Never]], str]


def call_and_format_exception_for_v8(fn: Callable[[], Never]) -> str:
    return "".join(format_exception_for_v8(call_and_capture_tbe(fn)))


def call_and_format_exception_for_python(fn: Callable[[], Never]) -> str:
    return "".join(call_and_capture_tbe(fn).format())


@pytest.fixture(
    params=[
        pytest.param(call_and_format_exception_for_v8, id="v8"),
        pytest.param(call_and_format_exception_for_python, id="py"),
    ]
)
def fmt_exc(request: pytest.FixtureRequest) -> FmtExc:
    return cast(FmtExc, request.param)


@pytest.fixture
def errors() -> ErrorScenario:
    return ErrorScenario()


def test_format_exception_for_v8__represents_simple_exception(
    snapshot: SnapshotFixture, fmt_exc: FmtExc, errors: ErrorScenario
) -> None:
    assert snapshot(".exc.txt") == fmt_exc(errors.raise_simple)


def test_format_exception_for_v8__represents_exception_with_context(
    snapshot: SnapshotFixture, fmt_exc: FmtExc, errors: ErrorScenario
) -> None:
    assert snapshot(".exc.txt") == fmt_exc(errors.raise_context)


def test_format_exception_for_v8__represents_ExceptionGroup(
    snapshot: SnapshotFixture, fmt_exc: FmtExc, errors: ErrorScenario
) -> None:
    assert snapshot(".exc.txt") == fmt_exc(errors.raise_group)


def test_format_exception_for_v8__represents_ExceptionGroup_with_context(
    snapshot: SnapshotFixture, fmt_exc: FmtExc, errors: ErrorScenario
) -> None:
    assert snapshot(".exc.txt") == fmt_exc(errors.raise_group_with_context)


def test_format_exception_for_v8__represents_nested_ExceptionGroups_with_context(
    snapshot: SnapshotFixture, fmt_exc: FmtExc, errors: ErrorScenario
) -> None:
    assert snapshot(".exc.txt") == fmt_exc(errors.raise_sub_group_with_context)
