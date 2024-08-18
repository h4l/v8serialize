from dataclasses import dataclass
from typing import ByteString, NewType, TypeAlias

from v8serialize.constants import ArrayBufferViewFlags, ArrayBufferViewTag

SharedArrayBufferId = NewType("SharedArrayBufferId", int)
TransferId = NewType("TransferId", int)


@dataclass(frozen=True, slots=True)
class ArrayBufferData:
    data: ByteString


@dataclass(frozen=True, slots=True)
class ResizableArrayBufferData:
    data: ByteString
    max_byte_length: int


@dataclass(frozen=True, slots=True)
class SharedArrayBufferData:
    buffer_id: SharedArrayBufferId


@dataclass(frozen=True, slots=True)
class ArrayBufferTransferData:
    transfer_id: TransferId


@dataclass(frozen=True, slots=True)
class ArrayBufferViewData:
    view_tag: ArrayBufferViewTag
    byte_offset: int
    byte_length: int
    flags: ArrayBufferViewFlags
    buffer: (
        ArrayBufferData
        | ResizableArrayBufferData
        | SharedArrayBufferData
        | ArrayBufferTransferData
    )


AnyArrayBufferData: TypeAlias = (
    ArrayBufferData
    | ResizableArrayBufferData
    | SharedArrayBufferData
    | ArrayBufferTransferData
)
