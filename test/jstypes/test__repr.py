from __future__ import annotations

from contextlib import ExitStack
from typing_extensions import Callable, Generator, TypeAlias

import pytest
from pytest_insta import SnapshotFixture

from v8serialize.jstypes._repr import (
    JSRepr,
    JSReprSettingsNotRestored,
    js_repr,
    js_repr_settings,
)
from v8serialize.jstypes.jsarray import JSArray
from v8serialize.jstypes.jsobject import JSObject


@pytest.fixture
def indented_js_repr() -> Generator[JSRepr, None, None]:
    with js_repr_settings(indent=2, maxlevel=6) as js_repr:
        yield js_repr


CheckRepr: TypeAlias = Callable[[object], None]


@pytest.fixture
def check_repr(snapshot: SnapshotFixture) -> CheckRepr:
    def check_repr(obj: object) -> None:
        assert snapshot() == repr(obj)

    return check_repr


#
# See snapshot files in test/jstypes/snapshots/*.txt
# These tests use https://github.com/vberlier/pytest-insta snapshots.
#


@pytest.mark.usefixtures("indented_js_repr")
def test_jsobject_repr(check_repr: CheckRepr) -> None:
    check_repr(JSObject())

    check_repr(JSObject({"z": 1, "b": 2, "c": 3}))

    check_repr(JSObject({"1001": "b", "1000": "a", "z": "Z", "x": "X"}, z="other"))

    # When some properties can't be represented as kwargs we don't split up the
    # properties, because order is significant.
    check_repr(JSObject({"foo bar": 1, "b": 2, "c": 3}))

    a = JSObject[object](a=1)
    a["b"] = a
    check_repr(a)

    check_repr(
        JSObject(a=JSArray([JSObject(name="Bob"), JSObject(name="Alice", id=2)]))
    )


def test_jsobject_maxjsobject(check_repr: CheckRepr) -> None:
    with js_repr_settings(maxjsobject=1):
        check_repr(JSObject(a=1, b=2))

        check_repr(JSObject({"!": 1, "@": 2}))

        check_repr(JSObject({0: "a"}, b=1))

    with js_repr_settings(indent=2, maxjsobject=1):
        check_repr(JSObject(a=1, b=2))

        check_repr(JSObject({"!": 1, "@": 2}))

        check_repr(JSObject({0: "a"}, one="b"))

        check_repr(JSObject({0: "a", 1: "b"}, two="c"))


@pytest.mark.usefixtures("indented_js_repr")
def test_jsarray_repr(check_repr: CheckRepr) -> None:
    check_repr(JSArray())

    check_repr(JSArray(["a", "b"]))

    check_repr(JSArray(["a", "b"], x="y"))

    check_repr(JSArray({"1000": "a"}))

    check_repr(JSArray({"1000": "a", "x": "y"}))

    check_repr(JSArray(x=1))

    check_repr(JSArray(x=1, y=2))

    check_repr(JSArray({"!": 1}))

    check_repr(JSArray({"!": 1, "!!": 2}))

    check_repr(JSArray({0: "a", "!": 1, "!!": 2}))

    a = JSArray[object](["a"])
    a.array.append(a)
    check_repr(a)

    check_repr(JSArray([JSObject({"names": JSArray(["Bill", "Bob"])})]))


def test_jsarray_maxlevel(check_repr: CheckRepr) -> None:
    with js_repr_settings(maxlevel=0):
        check_repr(JSArray(["a"]))


def test_jsarray_maxjsarray(check_repr: CheckRepr) -> None:
    with js_repr_settings(maxjsarray=1):
        check_repr(JSArray(c="C"))

        check_repr(JSArray(c="C", d="D"))

    with js_repr_settings(maxjsarray=1):
        check_repr(JSArray(**{"!": "C"}))

        check_repr(JSArray(**{"!": "C", "!!": "D"}))

    with js_repr_settings(maxjsarray=1):
        check_repr(JSArray(["a"]))

        check_repr(JSArray(["a", "b"]))

        check_repr(JSArray(["a", "b"], c="C"))

        check_repr(JSArray(["a", "b"], **{"!": "C"}))

    with js_repr_settings(indent=2, maxjsarray=1):
        check_repr(JSArray(c="C"))

        check_repr(JSArray(c="C", d="D"))

    with js_repr_settings(indent=2, maxjsarray=1):
        check_repr(JSArray(**{"!": "C"}))

        check_repr(JSArray(**{"!": "C", "!!": "D"}))

    with js_repr_settings(indent=2, maxjsarray=1):
        check_repr(JSArray(["a"]))

        check_repr(JSArray(["a", "b"]))

        check_repr(JSArray(["a", "b"], c="C"))

        check_repr(JSArray(["a", "b"], **{"!": "C"}))


def test_js_repr_settings__warns_on_close_if_settings_cannot_be_restored() -> None:
    with js_repr_settings(force_restore=True):
        assert js_repr("abc") == "'abc'"
        with ExitStack() as stack:
            with pytest.warns(JSReprSettingsNotRestored):
                with js_repr_settings(maxstring=1, fillvalue="<snip>"):
                    assert js_repr("abc") == "<snip>"

                    stack.enter_context(js_repr_settings(fillvalue="<chop>"))
                    assert js_repr("abc") == "<chop>"
            assert js_repr("abc") == "<chop>"
        # Inner js_repr_settings() restored the outer one's settings as it outlived
        # the outer. We could probably make the overrides work in a more elaborate
        # way to avoid this quirk.
        assert js_repr("abc") == "<snip>"

    # Fixed with our outermost context forcing things
    assert js_repr("abc") == "'abc'"
