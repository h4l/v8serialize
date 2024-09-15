from __future__ import annotations

import operator
from functools import reduce

import pytest
from packaging.version import Version

from v8serialize._errors import JSRegExpV8CodecError
from v8serialize._pycompat.re import RegexFlag
from v8serialize.constants import (
    JSErrorName,
    JSRegExpFlag,
    SerializationErrorTag,
    SerializationFeature,
    SerializationTag,
    SymbolicVersion,
)


def test_SerializationTag() -> None:
    assert int(SerializationTag.kBeginJSObject) in SerializationTag
    assert -1 not in SerializationTag
    assert 0xFFFF not in SerializationTag
    assert SerializationTag(int(SerializationTag.kRegExp)) is SerializationTag.kRegExp


def test_SerializationErrorTag() -> None:
    assert SerializationErrorTag.Message in SerializationErrorTag
    assert int(SerializationErrorTag.Message) in SerializationErrorTag
    assert -1 not in SerializationErrorTag
    assert 0xFFFF not in SerializationErrorTag
    assert (
        SerializationErrorTag(int(SerializationErrorTag.Cause))
        is SerializationErrorTag.Cause
    )


def test_RegExpFlag() -> None:
    assert JSRegExpFlag.Global == 1  # type: ignore[comparison-overlap]
    assert JSRegExpFlag.UnicodeSets == 1 << 8

    assert str(JSRegExpFlag.Global) == "g"
    assert str(JSRegExpFlag.UnicodeSets) == "v"

    assert str(JSRegExpFlag.Global | JSRegExpFlag.UnicodeSets) == "gv"

    assert str(JSRegExpFlag(0b111111111)) == "dgilmsuvy"

    assert JSRegExpFlag.IgnoreCase.as_python_flags() == RegexFlag.IGNORECASE
    assert JSRegExpFlag.Multiline.as_python_flags() == RegexFlag.MULTILINE

    assert (JSRegExpFlag.IgnoreCase | JSRegExpFlag.Multiline).as_python_flags() == (
        RegexFlag.IGNORECASE | RegexFlag.MULTILINE
    )
    assert JSRegExpFlag.Global.as_python_flags() == RegexFlag.NOFLAG

    # Linear has no equivalent in Python, so its presence invalidates tags its with
    assert JSRegExpFlag.Linear.as_python_flags(throw=False) is None
    assert (JSRegExpFlag.Multiline | JSRegExpFlag.Linear).as_python_flags(
        throw=False
    ) is None
    assert (
        JSRegExpFlag.Multiline | JSRegExpFlag.Linear | JSRegExpFlag.IgnoreCase
    ).as_python_flags(throw=False) is None

    with pytest.raises(
        JSRegExpV8CodecError,
        match=r"No equivalent Python flags exist for JSRegExp\.Linear",
        # ValueError, match=r"No equivalent Python flags exist for JSRegExp\.Linear"
    ):
        assert (JSRegExpFlag.Multiline | JSRegExpFlag.Linear).as_python_flags()


def test_RegExpFlag__canonical() -> None:
    for f in JSRegExpFlag:
        assert f.canonical == f

    all: JSRegExpFlag = reduce(operator.or_, JSRegExpFlag)  # type: ignore[assignment]
    assert all.canonical == all
    non_canonical = JSRegExpFlag(0xFFF)
    assert list(non_canonical) == list(all)
    assert non_canonical != all
    assert non_canonical.canonical == all

    assert JSRegExpFlag(0).canonical == 0


def test_RegExpFlag__from_python_flags() -> None:
    assert JSRegExpFlag.from_python_flags(RegexFlag.NOFLAG) == (JSRegExpFlag.NoFlag)

    assert JSRegExpFlag.from_python_flags(RegexFlag.MULTILINE | RegexFlag.DOTALL) == (
        JSRegExpFlag.Multiline | JSRegExpFlag.DotAll
    )

    with pytest.raises(
        JSRegExpV8CodecError,
        match=r"No equivalent JavaScript RegExp flags exist for RegexFlag\.VERBOSE",
    ):
        assert JSRegExpFlag.from_python_flags(RegexFlag.MULTILINE | RegexFlag.VERBOSE)


def test_ErrorTag() -> None:
    assert SerializationErrorTag.EvalErrorPrototype == ord("E")


def test_SerializationFeature() -> None:
    assert SerializationFeature.CircularErrorCause.first_v8_version == Version(
        "12.1.109"
    )
    assert (
        SerializationFeature.CircularErrorCause.first_v8_version
        > SerializationFeature.MaxCompatibility.first_v8_version
    )


def test_SerializationFeature__for_name() -> None:
    assert (
        SerializationFeature.for_name("CircularErrorCause")
        is SerializationFeature.CircularErrorCause
    )

    with pytest.raises(LookupError, match=r"^Frob$"):
        SerializationFeature.for_name("Frob")


@pytest.mark.parametrize(
    "v8_version, features",
    [
        (Version("0"), None),
        (Version("10.0.28"), None),
        (Version("10.0.28"), None),
        (Version("10.0.29"), SerializationFeature.MaxCompatibility),
        (Version("10.6.0"), SerializationFeature.MaxCompatibility),
        (Version("10.7.123"), SerializationFeature.RegExpUnicodeSets),
        ("10.7.123", SerializationFeature.RegExpUnicodeSets),
        (
            Version("15.0.0"),
            # Float16Array cannot be included as its version is not released
            ~SerializationFeature.Float16Array,
        ),
        (SymbolicVersion.Unreleased, ~SerializationFeature.MaxCompatibility),
    ],
)
def test_SerializationFeature__supported_by(
    v8_version: Version, features: SerializationFeature | None
) -> None:
    if features is None:
        with pytest.raises(LookupError, match=r"V8 version .+ is earlier than"):
            SerializationFeature.supported_by(v8_version=v8_version)
    else:
        assert SerializationFeature.supported_by(v8_version=v8_version) == features


def test_JSErrorName() -> None:
    assert str(JSErrorName.Error) == "Error"
    assert str(JSErrorName.Error) in JSErrorName
    assert (
        JSErrorName.SyntaxError.error_tag == SerializationErrorTag.SyntaxErrorPrototype
    )


def test_SymbolicVersion() -> None:
    assert SymbolicVersion.Unreleased > Version("0.0.0")
    assert Version("0.0.0") < SymbolicVersion.Unreleased
    assert SymbolicVersion.Unreleased > Version("99999999999.0.0")
    assert Version("99999999999.0.0") < SymbolicVersion.Unreleased
