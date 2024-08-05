import struct
from dataclasses import dataclass, field

from v8serialize.constants import SerializationTag
from v8serialize.decorators import tag


def _encode_zigzag(number: int) -> int:
    return abs(number * 2) - (number < 0)


@dataclass(slots=True)
class WritableTagStream:
    data: bytearray = field(default_factory=bytearray)

    @property
    def pos(self) -> int:
        return len(self.data)

    def write_tag(self, tag: SerializationTag) -> None:
        self.data.append(tag)

    def write_varint(self, n: int) -> None:
        if n < 0:
            raise ValueError(f"varint must be non-negative: {n}")
        while True:
            uint7 = n & 0b1111111
            n >>= 7
            if n == 0:
                self.data.append(uint7)
                return
            self.data.append(uint7 | 0b10000000)

    def write_zigzag(self, n: int) -> None:
        self.write_varint(_encode_zigzag(n))

    @tag(SerializationTag.kDouble)
    def write_double(self, value: float) -> None:
        self.data.extend(struct.pack("<d", value))

    def write_string_onebyte(self, value: str) -> None:
        """Encode a OneByte string, which is latin1-encoded text."""
        try:
            encoded = value.encode("latin1")
        except UnicodeEncodeError as e:
            raise ValueError(
                "Attempted to encode non-latin1 string in OneByte representation"
            ) from e
        self.write_tag(SerializationTag.kOneByteString)
        self.write_varint(len(encoded))
        self.data.extend(encoded)
