from __future__ import annotations

import functools
import inspect
import struct
from abc import ABC, abstractmethod
from contextlib import AbstractContextManager
from dataclasses import FrozenInstanceError, dataclass, field
from enum import Enum
from types import TracebackType
from typing import (
    TYPE_CHECKING,
    Any,
    ByteString,
    Generic,
    Literal,
    Self,
    Sized,
    TypeAlias,
    overload,
)

from v8serialize._values import (
    AnyArrayBuffer,
    AnyArrayBufferTransfer,
    AnyArrayBufferView,
    AnySharedArrayBuffer,
    SharedArrayBufferId,
    TransferId,
)
from v8serialize.constants import ArrayBufferViewTag
from v8serialize.errors import V8CodecError

if TYPE_CHECKING:
    from typing_extensions import Buffer, TypeVar

    AnyBuffer: TypeAlias = ByteString | Buffer
    AnyBufferT = TypeVar("AnyBufferT", bound=AnyBuffer, default=AnyBuffer)
    BufferT = TypeVar("BufferT", bound=ByteString, default=ByteString)
else:
    from typing import TypeVar

    AnyBufferT = TypeVar("AnyBufferT")
    BufferT = TypeVar("BufferT")

TypeT = TypeVar("TypeT", bound=type)


def frozen_setattr(cls: type, name: str, value: object) -> None:
    raise FrozenInstanceError(f"Cannot assign to field {name!r}")


def frozen(cls: TypeT) -> TypeT:
    """Disable `__setattr__`, much like @dataclass(frozen=True)."""
    cls.__setattr__ = frozen_setattr  # type: ignore[method-assign,assignment]
    return cls


def get_buffer(buffer: Buffer, flags: int | inspect.BufferFlags = 0) -> memoryview:
    # Python buffer protocol API only available from Python 3.12
    if hasattr(buffer, "__buffer__"):
        return buffer.__buffer__(flags)
    return memoryview(buffer)


@dataclass(frozen=True, slots=True)
class BaseJSArrayBuffer(ABC):
    @abstractmethod
    def __buffer__(self, flags: int) -> memoryview: ...


@dataclass(frozen=True, slots=True, init=False)
class JSArrayBuffer(
    AnyArrayBuffer,
    Generic[BufferT],
    AbstractContextManager["JSArrayBuffer[BufferT]"],
    ABC,
):
    _data: BufferT
    max_byte_length: int
    resizable: bool

    @overload
    def __init__(
        self,
        data: AnyBuffer | None = None,
        *,
        max_byte_length: int | None = None,
        resizable: bool | None = None,
        copy_data: bool | None = None,
        readonly: bool | None = None,
    ) -> None: ...

    @overload
    def __init__(
        self,
        byte_length: int | None = None,
        /,
        *,
        max_byte_length: int | None = None,
        resizable: bool | None = None,
        copy_data: bool | None = None,
        readonly: bool | None = None,
    ) -> None: ...

    def __init__(
        self,
        data: AnyBuffer | None | int = None,
        byte_length: int | None = None,
        *,
        max_byte_length: int | None = None,
        resizable: bool | None = None,
        copy_data: bool | None = None,
        readonly: bool | None = None,
    ) -> None:
        if isinstance(data, int):
            byte_length = data
            data = None
        if byte_length is not None:  # one of byte_length and data can be set
            data = None

        resizable = resizable is True or max_byte_length is not None
        copy_data = True if copy_data is None else copy_data
        readonly = False if copy_data is None else readonly

        if resizable is True and readonly is True:
            raise ValueError("JSArrayBuffer cannot be both resizable and readonly")

        if data is not None:
            if isinstance(data, memoryview):
                # Open our own memoryview of the source so that the caller can
                # be responsible for releasing their memoryview without
                # affecting us.
                data = data[:]

            if copy_data:
                data = bytes(data) if readonly else bytearray(data)
            elif readonly and not isinstance(data, bytes):
                data = memoryview(data).toreadonly()
        else:
            byte_length = byte_length or 0
            data = b"\x00" * byte_length if readonly else bytearray(byte_length)

        assert isinstance(data, Sized)
        max_byte_length = len(data) if max_byte_length is None else max_byte_length

        if resizable:
            if not isinstance(data, bytearray):
                assert not copy_data
                raise ValueError(
                    "data must be a bytearray when copy_data is False and "
                    "resizable is True"
                )
            assert isinstance(data, bytearray)
        if readonly:
            assert isinstance(data, bytes) or (
                isinstance(data, memoryview) and data.readonly
            )

        if len(data) > max_byte_length:
            raise ByteLengthJSArrayBufferError(
                "max_byte_length cannot be less than initial byte_length",
                byte_length=len(data),
                max_byte_length=max_byte_length,
            )

        # Need to borrow object's __setattr__, our frozen type disables ours.
        object.__setattr__(self, "_data", data)
        object.__setattr__(self, "max_byte_length", max_byte_length)
        object.__setattr__(self, "resizable", resizable)

    def resize(self, byte_length: int) -> None:
        if not self.resizable:
            raise ByteLengthJSArrayBufferError(
                "This JSArrayBuffer is not resizable",
                byte_length=byte_length,
                max_byte_length=self.max_byte_length,
            )
        if not (0 <= byte_length <= self.max_byte_length):
            raise ByteLengthJSArrayBufferError(
                "byte_length must be >= 0 and <= max_byte_length",
                byte_length=byte_length,
                max_byte_length=self.max_byte_length,
            )
        assert isinstance(self._data, bytearray)
        current_byte_length = len(self._data)

        if byte_length > current_byte_length:
            added_byte_count = byte_length - current_byte_length
            self._data.extend(bytearray(added_byte_count))
        else:
            del self._data[byte_length:]

    @property
    def data(self) -> memoryview:
        return self.__buffer__(inspect.BufferFlags.SIMPLE)

    def __enter__(self) -> JSArrayBuffer[BufferT]:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()
        return None

    def close(self) -> None:
        if isinstance(self.data, memoryview):
            self.data.release()

    def __buffer__(self, flags: int | inspect.BufferFlags) -> memoryview:
        return get_buffer(self._data, flags)[: self.max_byte_length]


@dataclass(frozen=True, slots=True)
class JSSharedArrayBuffer(AnySharedArrayBuffer, ABC):
    buffer_id: SharedArrayBufferId

    def __buffer__(self, flags: int) -> memoryview:
        raise NotImplementedError("Cannot access SharedArrayBuffer from Python")


@dataclass(frozen=True, slots=True)
class JSArrayBufferTransfer(AnyArrayBufferTransfer, ABC):
    transfer_id: TransferId

    def __buffer__(self, flags: int) -> memoryview:
        raise NotImplementedError("Cannot access ArrayBufferTransfer from Python")


if TYPE_CHECKING:
    AnyArrayBufferData: TypeAlias = (
        AnyBuffer | JSArrayBuffer | JSSharedArrayBuffer | JSArrayBufferTransfer
    )
    JSArrayBufferT = TypeVar(
        "JSArrayBufferT", bound=AnyArrayBufferData, default=AnyArrayBufferData
    )
else:
    JSArrayBufferT = TypeVar("JSArrayBufferT")


@dataclass(slots=True, init=False)
class JSArrayBufferView(Generic[JSArrayBufferT, AnyBufferT]):
    backing_buffer: JSArrayBufferT
    view_tag: ArrayBufferViewTag
    byte_offset: int
    byte_length: int | None
    readonly: bool
    view_format: ViewFormat

    def __init__(
        self,
        backing_buffer: JSArrayBufferT,
        *,
        view_tag: ArrayBufferViewTag = ArrayBufferViewTag.kUint8Array,
        byte_offset: int = 0,
        byte_length: int | None = None,
        readonly: bool = False,
    ) -> None:
        if byte_offset < 0:
            raise ValueError("byte_offset cannot be negative")
        self.backing_buffer = backing_buffer
        self.view_tag = view_tag
        self.byte_offset = byte_offset
        self.byte_length = byte_length
        self.view_format = ArrayBufferViewStructFormat(view_tag)

        # Can't access some backing buffers — they may raise NotImplementedError
        try:
            with memoryview(backing_buffer) as mv:
                buffer_readonly = mv.readonly
        except NotImplementedError:
            buffer_readonly = True

        self.readonly = buffer_readonly if readonly is None else readonly

    @property
    def is_length_tracking(self) -> bool:
        return self.byte_length is None

    @abstractmethod
    def get_buffer(self) -> AnyBufferT: ...

    def get_buffer_as_memoryview(self) -> memoryview:
        mv = memoryview(self.backing_buffer)
        if self.readonly:
            mv = mv.toreadonly()

        itemsize = self.view_format.itemsize
        struct_format = self.view_format.struct_format

        if self.byte_length is not None:
            # Fixed-length views must have a length that's multiple of the
            # itemsize.
            if self.byte_length % itemsize != 0:
                # memoryview would throw this itself, but let's be clear that
                # it's a problem with the data, not the implementation.
                raise ItemSizeJSArrayBufferError(
                    "byte_length is not a multiple of itemsize",
                    itemsize=itemsize,
                    byte_length=self.byte_length,
                )

            # Fixed-length views must be within the buffer's bounds.
            if self.byte_offset + self.byte_length > len(mv):
                raise BoundsJSArrayBufferError(
                    "byte_offset and byte_length are not within the bounds "
                    "of the backing buffer",
                    byte_offset=self.byte_offset,
                    byte_length=self.byte_length,
                    buffer_byte_length=len(mv),
                )
            mv = mv[self.byte_offset : self.byte_offset + self.byte_length]
            assert len(mv) == self.byte_length
            mv = mv.cast(struct_format)
        else:
            # Variable length buffers adjust their length to the largest
            # multiple of itemsize within the bounds.
            available_bytes = max(0, len(mv) - self.byte_offset)
            full_items, partial_items = divmod(available_bytes, itemsize)
            current_byte_length = full_items * itemsize
            mv = mv[self.byte_offset : self.byte_offset + current_byte_length]
            mv = mv.cast(struct_format)
            assert len(mv) == full_items

        return mv


TypedViewTag = Literal[
    ArrayBufferViewTag.kInt8Array,
    ArrayBufferViewTag.kUint8Array,
    ArrayBufferViewTag.kUint8ClampedArray,
    ArrayBufferViewTag.kInt16Array,
    ArrayBufferViewTag.kUint16Array,
    ArrayBufferViewTag.kInt32Array,
    ArrayBufferViewTag.kUint32Array,
    ArrayBufferViewTag.kFloat16Array,
    ArrayBufferViewTag.kFloat32Array,
    ArrayBufferViewTag.kFloat64Array,
    ArrayBufferViewTag.kBigInt64Array,
    ArrayBufferViewTag.kBigUint64Array,
]

if TYPE_CHECKING:
    ViewTagT = TypeVar("ViewTagT", bound=TypedViewTag, default=TypedViewTag)
    ElementT = TypeVar("ElementT", bound=int | float, default=int | float)
else:
    ViewTagT = TypeVar("ViewTagT")
    ElementT = TypeVar("ElementT")


class JSTypedArray(
    JSArrayBufferView[JSArrayBufferT, memoryview],
    AnyArrayBufferView,
    Generic[JSArrayBufferT, ViewTagT, ElementT],
):
    element_type: type[ElementT]
    view_tag: ViewTagT

    def __init__(
        self,
        backing_buffer: JSArrayBufferT,
        *,
        byte_offset: int = 0,
        byte_length: (
            int | None
        ) = None,  # TODO: serialized  data uses 0 when flags are resizable
        readonly: bool = False,
    ) -> None:
        super(JSTypedArray, self).__init__(
            backing_buffer,
            view_tag=self.view_tag,
            byte_offset=byte_offset,
            byte_length=byte_length,
            readonly=readonly,
        )

    # FIXME: memoryview is generic in typeshed, but mypy errors if I give it the
    #  ElementT annotation
    def get_buffer(self) -> memoryview:
        return self.get_buffer_as_memoryview()


class JSInt8Array(
    JSTypedArray[JSArrayBufferT, Literal[ArrayBufferViewTag.kInt8Array], int]
):
    element_type = int
    view_tag = ArrayBufferViewTag.kInt8Array


class JSUint8Array(
    JSTypedArray[JSArrayBufferT, Literal[ArrayBufferViewTag.kUint8Array], int]
):
    element_type = int
    view_tag = ArrayBufferViewTag.kUint8Array


class JSUint8ClampedArray(
    JSTypedArray[JSArrayBufferT, Literal[ArrayBufferViewTag.kUint8ClampedArray], int]
):
    element_type = int
    view_tag = ArrayBufferViewTag.kUint8ClampedArray


class JSInt16Array(
    JSTypedArray[JSArrayBufferT, Literal[ArrayBufferViewTag.kInt16Array], int]
):
    element_type = int
    view_tag = ArrayBufferViewTag.kInt16Array


class JSUint16Array(
    JSTypedArray[JSArrayBufferT, Literal[ArrayBufferViewTag.kUint16Array], int]
):
    element_type = int
    view_tag = ArrayBufferViewTag.kUint16Array


class JSInt32Array(
    JSTypedArray[JSArrayBufferT, Literal[ArrayBufferViewTag.kInt32Array], int]
):
    element_type = int
    view_tag = ArrayBufferViewTag.kInt32Array


class JSUint32Array(
    JSTypedArray[JSArrayBufferT, Literal[ArrayBufferViewTag.kUint32Array], int]
):
    element_type = int
    view_tag = ArrayBufferViewTag.kUint32Array


class JSFloat16Array(
    JSTypedArray[JSArrayBufferT, Literal[ArrayBufferViewTag.kFloat16Array], float]
):
    element_type = float
    view_tag = ArrayBufferViewTag.kFloat16Array


class JSFloat32Array(
    JSTypedArray[JSArrayBufferT, Literal[ArrayBufferViewTag.kFloat32Array], float]
):
    element_type = float
    view_tag = ArrayBufferViewTag.kFloat32Array


class JSFloat64Array(
    JSTypedArray[JSArrayBufferT, Literal[ArrayBufferViewTag.kFloat64Array], float]
):
    element_type = float
    view_tag = ArrayBufferViewTag.kFloat64Array


class JSBigInt64Array(
    JSTypedArray[JSArrayBufferT, Literal[ArrayBufferViewTag.kBigInt64Array], int]
):
    element_type = int
    view_tag = ArrayBufferViewTag.kBigInt64Array


class JSBigUint64Array(
    JSTypedArray[JSArrayBufferT, Literal[ArrayBufferViewTag.kBigUint64Array], int]
):
    element_type = int
    view_tag = ArrayBufferViewTag.kBigUint64Array


@dataclass(frozen=True)
class DataViewBuffer(AbstractContextManager["DataViewBuffer"]):
    buffer: memoryview

    def __buffer__(self, flags: int | inspect.BufferFlags) -> memoryview:
        return get_buffer(self.buffer, flags)

    def __enter__(self) -> Self:
        return self

    def __len__(self) -> int:
        return len(self.buffer)

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.buffer.__exit__(exc_type, exc_value, traceback)
        return None

    def read(self, struct_format: str, byte_offset: int) -> tuple[Any, ...]:
        buffer = self.buffer
        if byte_offset < 0 or (byte_offset + struct.calcsize(struct_format)) > len(
            buffer
        ):
            raise BoundsJSArrayBufferError(
                "Read is outside the bounds of the DataView",
                byte_offset=byte_offset,
                byte_length=struct.calcsize(struct_format),
                buffer_byte_length=len(self.buffer),
            )
        return struct.unpack_from(struct_format, self.buffer, byte_offset)

    def write(self, struct_format: str, byte_offset: int, *values: Any) -> None:
        buffer = self.buffer
        if byte_offset < 0 or (byte_offset + struct.calcsize(struct_format)) > len(
            buffer
        ):
            raise BoundsJSArrayBufferError(
                "Write is outside the bounds of the DataView",
                byte_offset=byte_offset,
                byte_length=struct.calcsize(struct_format),
                buffer_byte_length=len(self.buffer),
            )
        struct.pack_into(struct_format, buffer, byte_offset, *values)

    def get_bigint64(self, byte_offset: int, little_endian: bool = False) -> int:
        return self.read("<q" if little_endian else ">q", byte_offset)[0]  # type: ignore[no-any-return]

    def get_biguint64(self, byte_offset: int, little_endian: bool = False) -> int:
        return self.read("<Q" if little_endian else ">Q", byte_offset)[0]  # type: ignore[no-any-return]

    def get_float16(self, byte_offset: int, little_endian: bool = False) -> float:
        return self.read("<e" if little_endian else ">e", byte_offset)[0]  # type: ignore[no-any-return]

    def get_float32(self, byte_offset: int, little_endian: bool = False) -> float:
        return self.read("<f" if little_endian else ">f", byte_offset)[0]  # type: ignore[no-any-return]

    def get_float64(self, byte_offset: int, little_endian: bool = False) -> float:
        return self.read("<d" if little_endian else ">d", byte_offset)[0]  # type: ignore[no-any-return]

    def get_int16(self, byte_offset: int, little_endian: bool = False) -> int:
        return self.read("<h" if little_endian else ">h", byte_offset)[0]  # type: ignore[no-any-return]

    def get_int32(self, byte_offset: int, little_endian: bool = False) -> int:
        return self.read("<i" if little_endian else ">i", byte_offset)[0]  # type: ignore[no-any-return]

    def get_uint16(self, byte_offset: int, little_endian: bool = False) -> int:
        return self.read("<h" if little_endian else ">h", byte_offset)[0]  # type: ignore[no-any-return]

    def get_uint32(self, byte_offset: int, little_endian: bool = False) -> int:
        return self.read("<I" if little_endian else ">I", byte_offset)[0]  # type: ignore[no-any-return]

    def get_int8(self, byte_offset: int) -> int:
        return self.read("b", byte_offset)[0]  # type: ignore[no-any-return]

    def get_uint8(self, byte_offset: int) -> int:
        return self.read("B", byte_offset)[0]  # type: ignore[no-any-return]

    def set_bigint64(
        self, byte_offset: int, value: int, little_endian: bool = False
    ) -> None:
        self.write("<q" if little_endian else ">q", byte_offset, value)

    def set_biguint64(
        self, byte_offset: int, value: int, little_endian: bool = False
    ) -> None:
        self.write("<Q" if little_endian else ">Q", byte_offset, value)

    def set_float16(
        self, byte_offset: int, value: float, little_endian: bool = False
    ) -> None:
        self.write("<e" if little_endian else ">e", byte_offset, value)

    def set_float32(
        self, byte_offset: int, value: float, little_endian: bool = False
    ) -> None:
        self.write("<f" if little_endian else ">f", byte_offset, value)

    def set_float64(
        self, byte_offset: int, value: float, little_endian: bool = False
    ) -> None:
        self.write("<d" if little_endian else ">d", byte_offset, value)

    def set_int16(
        self, byte_offset: int, value: int, little_endian: bool = False
    ) -> None:
        self.write("<h" if little_endian else ">h", byte_offset, value)

    def set_int32(
        self, byte_offset: int, value: int, little_endian: bool = False
    ) -> None:
        self.write("<i" if little_endian else ">i", byte_offset, value)

    def set_uint16(
        self, byte_offset: int, value: int, little_endian: bool = False
    ) -> None:
        self.write("<H" if little_endian else ">H", byte_offset, value)

    def set_uint32(
        self, byte_offset: int, value: int, little_endian: bool = False
    ) -> None:
        self.write("<I" if little_endian else ">I", byte_offset, value)

    def set_int8(self, byte_offset: int, value: int) -> None:
        self.write("b", byte_offset, value)

    def set_uint8(self, byte_offset: int, value: int) -> None:
        self.write("B", byte_offset, value)


class JSDataView(JSArrayBufferView[JSArrayBufferT, DataViewBuffer]):
    def __init__(
        self,
        backing_buffer: JSArrayBufferT,
        byte_offset: int = 0,
        byte_length: int | None = None,
        readonly: bool = False,
    ) -> None:
        super().__init__(
            backing_buffer=backing_buffer,
            view_tag=ArrayBufferViewTag.kDataView,
            byte_offset=byte_offset,
            byte_length=byte_length,
            readonly=readonly,
        )

    def get_buffer(self) -> DataViewBuffer:
        return DataViewBuffer(self.get_buffer_as_memoryview())


@dataclass(slots=True, unsafe_hash=True, order=True)
class ViewFormat:
    view_tag: ArrayBufferViewTag
    struct_format: str
    view_type: type[JSTypedArray] | type[JSDataView]
    itemsize: int = field(init=False)

    def __post_init__(self) -> None:
        self.itemsize = struct.calcsize(self.struct_format)


@frozen
class ArrayBufferViewStructFormat(ViewFormat, Enum):
    Int8Array = ArrayBufferViewTag.kInt8Array, "b", JSInt8Array
    Uint8Array = ArrayBufferViewTag.kUint8Array, "B", JSUint8Array
    # Python doesn't distinguish between wrapping and clamped views, because
    # setting out-of-range values throws an error.
    Uint8ClampedArray = ArrayBufferViewTag.kUint8ClampedArray, "B", JSUint8ClampedArray
    Int16Array = ArrayBufferViewTag.kInt16Array, "h", JSInt16Array
    Uint16Array = ArrayBufferViewTag.kUint16Array, "H", JSUint16Array
    Int32Array = ArrayBufferViewTag.kInt32Array, "i", JSInt32Array
    Uint32Array = ArrayBufferViewTag.kUint32Array, "I", JSUint32Array
    Float16Array = ArrayBufferViewTag.kFloat16Array, "e", JSFloat16Array
    Float32Array = ArrayBufferViewTag.kFloat32Array, "f", JSFloat32Array
    Float64Array = ArrayBufferViewTag.kFloat64Array, "d", JSFloat64Array
    BigInt64Array = ArrayBufferViewTag.kBigInt64Array, "q", JSBigInt64Array
    BigUint64Array = ArrayBufferViewTag.kBigUint64Array, "Q", JSBigUint64Array
    # DataView doesn't have a single format, we use bytes format as a default.
    # As in accessing the buffer provides actual bytes objects, not integers.
    DataView = ArrayBufferViewTag.kDataView, "c", JSDataView

    @functools.lru_cache  # noqa: B019 # OK because static method
    @staticmethod
    def _missing_(arg: object) -> ArrayBufferViewStructFormat | None:
        # Allow looking up values by ArrayBufferViewTag enum value
        for value in ArrayBufferViewStructFormat:
            if value.view_tag is arg:
                return value
        return None

    if TYPE_CHECKING:

        def __init__(
            self, value: ArrayBufferViewTag | ArrayBufferViewStructFormat
        ) -> None: ...


def create_view(
    buffer: JSArrayBufferT,
    format: ArrayBufferViewTag | ArrayBufferViewStructFormat,
    *,
    byte_offset: int = 0,
    byte_length: int | None = None,
    readonly: bool = False,
) -> JSTypedArray | JSDataView:
    if isinstance(format, ArrayBufferViewTag):
        format = ArrayBufferViewStructFormat(format)
    return format.view_type(
        buffer,
        byte_offset=byte_offset,
        byte_length=byte_length,
        readonly=readonly,
    )


@dataclass(init=False)
class JSArrayBufferError(V8CodecError):
    pass


@dataclass(init=False)
class ByteLengthJSArrayBufferError(V8CodecError, ValueError):
    byte_length: int
    max_byte_length: int | None

    def __init__(
        self, message: str, *, byte_length: int, max_byte_length: int | None
    ) -> None:
        super(ByteLengthJSArrayBufferError, self).__init__(message)
        self.byte_length = byte_length
        self.max_byte_length = max_byte_length


@dataclass(init=False)
class ItemSizeJSArrayBufferError(JSArrayBufferError, ValueError):
    itemsize: int
    byte_length: int

    def __init__(self, message: str, itemsize: int, byte_length: int) -> None:
        super(ItemSizeJSArrayBufferError, self).__init__(message)
        self.itemsize = itemsize
        self.byte_length = byte_length


@dataclass(init=False)
class BoundsJSArrayBufferError(JSArrayBufferError, ValueError):
    byte_offset: int
    byte_length: int
    buffer_byte_length: int

    def __init__(
        self, message: str, byte_offset: int, byte_length: int, buffer_byte_length: int
    ):
        super(BoundsJSArrayBufferError, self).__init__(message)
        self.byte_offset = byte_offset
        self.byte_length = byte_length
        self.buffer_byte_length = buffer_byte_length
