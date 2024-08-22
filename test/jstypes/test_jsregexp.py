import re

import pytest

from v8serialize.constants import JSRegExpFlag
from v8serialize.errors import JSRegExpV8CodecError
from v8serialize.jstypes.jsregexp import JSRegExp


@pytest.mark.parametrize(
    "jsregexp,msg",
    [
        pytest.param(
            JSRegExp(r".*", JSRegExpFlag.Linear),
            "No equivalent Python flags exist for JSRegExp.Linear",
            id="invalid_flags",
        ),
        pytest.param(
            JSRegExp(r"\cJ"),
            "bad escape \\c at position 0",
            id="invalid_syntax",
        ),
    ],
)
def test_compile__incompatible(jsregexp: JSRegExp, msg: str) -> None:
    with pytest.raises(
        JSRegExpV8CodecError,
        match=re.escape(f"JSRegExp is not a valid Python re.Pattern: {msg}"),
    ):
        jsregexp.as_python_pattern()

    assert jsregexp.as_python_pattern(throw=False) is None


def test_from_python_pattern() -> None:
    assert JSRegExp.from_python_pattern(
        re.compile(".*", re.UNICODE | re.DOTALL)
    ) == JSRegExp(".*", JSRegExpFlag.UnicodeSets | JSRegExpFlag.DotAll)

    assert JSRegExp.from_python_pattern(re.compile(b".*")) == JSRegExp(".*")

    with pytest.raises(
        JSRegExpV8CodecError,
        match=re.escape(
            "Python re.Pattern flags cannot be represented by JavaScript RegExp: "
            "No equivalent JavaScript RegExp flags exist for RegexFlag.VERBOSE"
        ),
    ):
        JSRegExp.from_python_pattern(re.compile("", re.VERBOSE))

    assert JSRegExp.from_python_pattern(re.compile("", re.VERBOSE), throw=False) is None
