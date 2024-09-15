from __future__ import annotations

from array import array

import pytest

from v8serialize._pycompat.typing import (
    Buffer,
    ReadableBinary,
    get_buffer,
    is_readable_binary,
)


@pytest.mark.parametrize(
    "buffer", [b"a", bytearray(b"a"), memoryview(b"a"), array("B", b"a")]
)
def test_is_readable_binary(buffer: Buffer) -> None:
    assert is_readable_binary(buffer)
    assert read_something(buffer) == b"a"[0]

    # getitem slice must return a ReadableBinary, not just Sequence[int]
    piece = buffer[:1]
    assert read_something(piece) == b"a"[0]

    # regular types can be assigned to a ReadableBinary var
    rb: ReadableBinary = b"abc"
    assert rb


@pytest.mark.parametrize(
    "buffer",
    [
        b"a",
        bytearray(b"a"),
        memoryview(b"a"),
        memoryview(b"a").cast("b", (1, 1)),
        array("B", b"a"),
        # get_buffer returns flat uint8 memoryview
        array("I", [ord(b"a")] * 4),
    ],
)
def test_get_buffer(buffer: Buffer) -> None:
    mv = get_buffer(buffer)
    assert mv.format == "B"
    assert mv.ndim == 1
    assert mv.itemsize == 1
    assert mv[0] == b"a"[0]


def read_something(data: ReadableBinary) -> int:
    return data[0]
