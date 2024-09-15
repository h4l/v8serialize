from __future__ import annotations

from array import array
from typing import TYPE_CHECKING, Sequence, Union, overload

if TYPE_CHECKING:
    from typing_extensions import Buffer as Buffer
    from typing_extensions import TypeAlias, TypeGuard

    class BufferSequence(Sequence[int], Buffer):
        """Binary data such as `bytes`, `bytearray`, `array.array` and `memoryview`."""

        @overload  # type: ignore[override]
        def __getitem__(self, index: slice, /) -> BufferSequence: ...

        @overload
        def __getitem__(self, index: int, /) -> int: ...

        def __getitem__(self, index: int | slice, /) -> int | BufferSequence: ...

else:

    try:
        from collections.abc import Buffer
    except ImportError:
        from abc import ABC, abstractmethod

        class Buffer(ABC):
            """Runtime placeholder for collections.abc."""

            @abstractmethod
            def __buffer__(self, flags: int) -> memoryview: ...

    class BufferSequence(Sequence, Buffer):
        """Binary data, like `bytes`, `bytearray`, `array.array` and `memoryview`."""


ReadableBinary: TypeAlias = Union[
    "bytes | bytearray | memoryview | array[int] | BufferSequence"
]
"""Binary data such as bytes, bytearray, array and memoryview."""


def is_readable_binary(buffer: Buffer) -> TypeGuard[ReadableBinary]:
    """
    True if a binary value can be read directly without wrapping in a `memoryview`.
    """
    return isinstance(buffer, (bytes, bytearray, memoryview, array, Sequence))
