from __future__ import annotations

from re import ASCII as ASCII
from re import DOTALL as DOTALL
from re import IGNORECASE as IGNORECASE
from re import LOCALE as LOCALE
from re import MULTILINE as MULTILINE
from re import UNICODE as UNICODE
from re import VERBOSE as VERBOSE

from v8serialize._pycompat.enum import IterableIntFlag


# 3.9 doesn't define NOFLAG, and default IntFlag is not iterable in 3.9.
class RegexFlag(IterableIntFlag):
    NOFLAG = 0
    ASCII = ASCII
    DOTALL = DOTALL
    IGNORECASE = IGNORECASE
    LOCALE = LOCALE
    MULTILINE = MULTILINE
    UNICODE = UNICODE
    VERBOSE = VERBOSE
