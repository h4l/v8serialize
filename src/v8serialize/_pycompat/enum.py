from __future__ import annotations

import sys
from enum import EnumMeta, Flag, IntFlag
from typing import TYPE_CHECKING, Iterator

if TYPE_CHECKING:
    from typing_extensions import Self


class ContainsValueEnumMeta(EnumMeta):
    def __contains__(cls, value: object) -> bool:
        if value in cls._value2member_map_:
            return True
        return False


if sys.version_info < (3, 12):
    from enum import Enum

    class StrEnum(str, Enum, metaclass=ContainsValueEnumMeta):
        def __str__(self) -> str:
            assert self._value_ is not self
            return str(self._value_)

else:
    from enum import StrEnum as StrEnum  # noqa: F401  # re-export


if sys.version_info < (3, 11):
    # Even though IntFlag is just (int, Flag), MyPy errors if we subclass
    # (IterableFlag, IntFlag), so we have to redundantly define this for both
    # types.
    class IterableFlag(Flag):
        def __iter__(self) -> Iterator[Self]:
            for flag in type(self):
                if self & flag:
                    yield flag

    class IterableIntFlag(IntFlag):
        def __iter__(self) -> Iterator[Self]:
            for flag in type(self):
                if self & flag:
                    yield flag

else:

    class IterableFlag(Flag):
        pass

    class IterableIntFlag(IntFlag):
        pass


# In py3.12 you can do things like `42 in SomeIntEnum`, returning True/False.
# In previous versions you get a TypeError.
if sys.version_info < (3, 12):
    from enum import IntEnum as _IntEnum

    class IntEnum(_IntEnum, metaclass=ContainsValueEnumMeta):
        def __str__(self) -> str:
            assert self._value_ is not self
            return str(self._value_)

else:
    from enum import IntEnum as IntEnum  # noqa: F401  # re-export
