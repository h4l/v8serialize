from __future__ import annotations

import re

import pytest
from hypothesis import given

from test.strategies import js_regexp_flags
from v8serialize._errors import JSRegExpV8SerializeError
from v8serialize.constants import JSRegExpFlag
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
        JSRegExpV8SerializeError,
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
        JSRegExpV8SerializeError,
        match=re.escape(
            "Python re.Pattern flags cannot be represented by JavaScript RegExp: "
            "No equivalent JavaScript RegExp flags exist for RegexFlag.VERBOSE"
        ),
    ):
        JSRegExp.from_python_pattern(re.compile("", re.VERBOSE))

    assert JSRegExp.from_python_pattern(re.compile("", re.VERBOSE), throw=False) is None


def test_empty_source_is_non_capturing_group() -> None:
    assert JSRegExp(source="").source == "(?:)"


@given(any_flags=js_regexp_flags())
def test_flags_cannot_have_both_unicode_flags_set(any_flags: JSRegExpFlag) -> None:
    with pytest.raises(
        ValueError, match=r"The Unicode and UnicodeSets flags cannot be set together"
    ):
        JSRegExp("", flags=any_flags | JSRegExpFlag.Unicode | JSRegExpFlag.UnicodeSets)
