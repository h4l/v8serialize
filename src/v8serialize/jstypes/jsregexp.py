from __future__ import annotations

import re
from dataclasses import dataclass, field
from re import Pattern, compile
from typing import AnyStr, Literal, overload

from v8serialize._errors import JSRegExpV8SerializeError
from v8serialize._pycompat.re import RegexFlag
from v8serialize.constants import JSRegExpFlag


@dataclass(frozen=True, order=True, slots=True)
class JSRegExp:
    """The data represented by a [JavaScript RegExp].

    Note that while Python and JavaScript Regular Expressions are similar, they
    each have features and syntax not supported by the other. Simple expressions
    will work the same in both languages, but this is not the case in general.

    **`JSRegExp` does not support matching text with the RegExp**, but
    [`as_python_pattern()`] can work for patterns that use compatible syntax and
    flags.

    [`as_python_pattern()`]: `v8serialize.jstypes.JSRegExp.as_python_pattern`
    [JavaScript RegExp]: https://developer.mozilla.org/en-US/docs/Web/\
JavaScript/Reference/Global_Objects/RegExp
    """

    source: str
    flags: JSRegExpFlag = field(default=JSRegExpFlag.NoFlag)

    def __post_init__(self) -> None:
        if self.source == "":
            # JavaScript regexes cannot be empty, because the slash-delimited
            # literal syntax would be the same as a comment. Empty regexes are
            # represented as an empty non-capturing group.
            object.__setattr__(self, "source", "(?:)")
        if self.flags & JSRegExpFlag.Unicode and self.flags & JSRegExpFlag.UnicodeSets:
            raise ValueError(
                "The Unicode and UnicodeSets flags cannot be set together: "
                "Setting both is a syntax error in JavaScript because they "
                "enable incompatible interpretations of the RegExp source."
            )

    @overload
    @staticmethod
    def from_python_pattern(
        pattern: re.Pattern[AnyStr], throw: Literal[False]
    ) -> JSRegExp | None: ...

    @overload
    @staticmethod
    def from_python_pattern(
        pattern: re.Pattern[AnyStr], throw: Literal[True] = True
    ) -> JSRegExp: ...

    @staticmethod
    def from_python_pattern(
        pattern: re.Pattern[AnyStr], throw: bool = True
    ) -> JSRegExp | None:
        """Naively create a JSRegExp with an un-translated Python re.Pattern.

        As with `as_python_pattern()` this can result in JSRegExp objects that
        won't behave on the JavaScript side in the same way as in Python.

        This can fail if the Python pattern has `re.VERBOSE` set, as there's
        no equivalent JavaScript flag.
        """
        if isinstance(pattern.pattern, bytes):
            source = pattern.pattern.decode()
        else:
            source = pattern.pattern
        try:
            flags = JSRegExpFlag.from_python_flags(RegexFlag(pattern.flags))
        except JSRegExpV8SerializeError as e:
            if throw:
                raise JSRegExpV8SerializeError(
                    f"Python re.Pattern flags cannot be represented by "
                    f"JavaScript RegExp: {e}"
                ) from e
            return None
        return JSRegExp(source, flags=flags)

    @overload
    def as_python_pattern(self, throw: Literal[False]) -> Pattern[str] | None: ...

    @overload
    def as_python_pattern(self, throw: Literal[True] = True) -> Pattern[str]: ...

    def as_python_pattern(self, throw: bool = True) -> Pattern[str] | None:
        """Naively compile the JavaScript RegExp as a Python re.Pattern.

        The pattern may fail to compile due to syntax incompatibility, or may
        compile but behave incorrectly due to differences between Python and
        JavaScript's regular expression support.
        """
        # There is https://github.com/Zac-HD/js-regex but it seems to be a proof
        # of concept in that it doesn't fully parse and translate the regex AST,
        # so some patterns still don't work.
        try:
            return compile(self.source, self.flags.as_python_flags())
        except (JSRegExpV8SerializeError, re.error) as e:
            if throw:
                raise JSRegExpV8SerializeError(
                    f"JSRegExp is not a valid Python re.Pattern: {e}"
                ) from e
            return None
