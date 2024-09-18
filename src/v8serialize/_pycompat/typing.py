from __future__ import annotations

from array import array
from typing import TYPE_CHECKING, Sequence, Union, overload

from v8serialize._pycompat.inspect import BufferFlags

if TYPE_CHECKING:
    from typing_extensions import Buffer as Buffer
    from typing_extensions import TypeAlias, TypeGuard

    class BufferSequence(Sequence[int], Buffer):
        """
        Binary data, like `bytes`, `bytearray`, `array.array` and `memoryview`.

        Essentially a `Sequence[int]` that's also a `Buffer`.
        """

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
            """An alias of [`collections.abc.Buffer`](`collections.abc.Buffer`)."""

            @abstractmethod
            def __buffer__(self, flags: int) -> memoryview: ...

    class BufferSequence(Sequence, Buffer):
        """
        A `Sequence[int]` that's also a `Buffer`.

        Essentially binary data, like `bytes`, `bytearray`, `array.array` and
        `memoryview`.
        """


ReadableBinary: TypeAlias = Union[
    "bytes | bytearray | memoryview | array[int] | BufferSequence"
]
"""
Binary data such as `bytes`, `bytearray`, `array.array` and `memoryview`.

Can also be any [`BufferSequence`](`v8serialize.BufferSequence`).
"""


def is_readable_binary(buffer: Buffer) -> TypeGuard[ReadableBinary]:
    """Return True if a binary value can be read without wrapping in a `memoryview`."""
    return isinstance(buffer, (bytes, bytearray, memoryview, array, Sequence))


def get_buffer(
    buffer: Buffer, flags: int | BufferFlags = BufferFlags.SIMPLE
) -> memoryview:
    """Get a bytes-format memoryview of a value supporting the Buffer protocol.

    Returns
    -------
    :
        A memoryview with itemsize 1, 1 dimension and `B` (uint8) format.
    """
    # Python buffer protocol API only available from Python 3.12
    if hasattr(buffer, "__buffer__"):
        buf = buffer.__buffer__(flags)
    else:
        buf = memoryview(buffer)
    if not (buf.format == "B" and buf.ndim == 1 and buf.itemsize == 1):
        buf = buf.cast("B")
    return buf
