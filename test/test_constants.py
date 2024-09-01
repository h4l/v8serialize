from __future__ import annotations

import operator
import re
from functools import reduce

import pytest
from packaging.version import Version

from v8serialize.constants import (
    JSRegExpFlag,
    SerializationErrorTag,
    SerializationFeature,
    SymbolicVersion,
)
from v8serialize.errors import JSRegExpV8CodecError


def test_RegExpFlag() -> None:
    assert JSRegExpFlag.Global == 1  # type: ignore[comparison-overlap]
    assert JSRegExpFlag.UnicodeSets == 1 << 8

    assert str(JSRegExpFlag.Global) == "g"
    assert str(JSRegExpFlag.UnicodeSets) == "v"

    assert str(JSRegExpFlag.Global | JSRegExpFlag.UnicodeSets) == "gv"

    assert str(JSRegExpFlag(0b111111111)) == "dgilmsuvy"

    assert JSRegExpFlag.IgnoreCase.as_python_flags() == re.IGNORECASE
    assert JSRegExpFlag.Multiline.as_python_flags() == re.MULTILINE

    assert (JSRegExpFlag.IgnoreCase | JSRegExpFlag.Multiline).as_python_flags() == (
        re.IGNORECASE | re.MULTILINE
    )
    assert JSRegExpFlag.Global.as_python_flags() == re.RegexFlag.NOFLAG

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

    assert JSRegExpFlag.from_python_flags(re.RegexFlag.NOFLAG) == (JSRegExpFlag.NoFlag)

    assert JSRegExpFlag.from_python_flags(
        re.RegexFlag.MULTILINE | re.RegexFlag.DOTALL
    ) == (JSRegExpFlag.Multiline | JSRegExpFlag.DotAll)

    with pytest.raises(
        JSRegExpV8CodecError,
        match=r"No equivalent JavaScript RegExp flags exist for RegexFlag\.VERBOSE",
    ):
        assert JSRegExpFlag.from_python_flags(
            re.RegexFlag.MULTILINE | re.RegexFlag.VERBOSE
        )


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
            ~SerializationFeature.MaxCompatibility - SerializationFeature.Float16Array,
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


def test_SymbolicVersion() -> None:
    assert SymbolicVersion.Unreleased > Version("0.0.0")
    assert Version("0.0.0") < SymbolicVersion.Unreleased
    assert SymbolicVersion.Unreleased > Version("99999999999.0.0")
    assert Version("99999999999.0.0") < SymbolicVersion.Unreleased
