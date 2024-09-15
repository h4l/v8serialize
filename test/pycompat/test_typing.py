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
    "buffer", [b"a", bytearray(b"a"), memoryview(b"a"), array("B", b"a")]
)
def test_get_buffer(buffer: Buffer) -> None:
    assert get_buffer(buffer)[0] == b"a"[0]


def read_something(data: ReadableBinary) -> int:
    return data[0]
