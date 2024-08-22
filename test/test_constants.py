import operator
import re
from functools import reduce

import pytest

from v8serialize.constants import JSRegExpFlag
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
