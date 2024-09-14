from __future__ import annotations

import functools
import struct
from abc import ABC, abstractmethod
from collections.abc import ByteString, Sized
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass, field
from enum import Enum
from types import TracebackType
from typing import (
    TYPE_CHECKING,
    Any,
    ClassVar,
    ContextManager,
    Generator,
    Generic,
    Literal,
    cast,
    overload,
)

from v8serialize._enums import frozen
from v8serialize._pycompat.dataclasses import slots_if310
from v8serialize._pycompat.inspect import BufferFlags
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
    from typing_extensions import Buffer, Self, TypeAlias, TypeVar

    AnyBuffer: TypeAlias = "ByteString | Buffer"
    AnyBufferT = TypeVar("AnyBufferT", bound=AnyBuffer, default=AnyBuffer)
    BufferT = TypeVar("BufferT", bound=ByteString, default=ByteString)
else:
    from typing import TypeVar

    AnyBufferT = TypeVar("AnyBufferT")
    BufferT = TypeVar("BufferT")


def get_buffer(
    buffer: Buffer, flags: int | BufferFlags = BufferFlags.SIMPLE
) -> memoryview:
    # Python buffer protocol API only available from Python 3.12
    if hasattr(buffer, "__buffer__"):
        return buffer.__buffer__(flags)
    return memoryview(buffer)


@dataclass(frozen=True, **slots_if310())
class BaseJSArrayBuffer(ABC):
    @abstractmethod
    def __buffer__(self, flags: int) -> memoryview: ...


@BaseJSArrayBuffer.register
@dataclass(frozen=True, init=False, **slots_if310())
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
        return self.__buffer__(BufferFlags.SIMPLE)

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

    def __buffer__(self, flags: int | BufferFlags) -> memoryview:
        return get_buffer(self._data, flags)[: self.max_byte_length]


@BaseJSArrayBuffer.register
@dataclass(frozen=True, **slots_if310())
class JSSharedArrayBuffer(AnySharedArrayBuffer, ABC):
    buffer_id: SharedArrayBufferId

    def __buffer__(self, flags: int) -> memoryview:
        raise NotImplementedError("Cannot access SharedArrayBuffer from Python")


@BaseJSArrayBuffer.register
@dataclass(frozen=True, **slots_if310())
class JSArrayBufferTransfer(AnyArrayBufferTransfer, ABC):
    transfer_id: TransferId

    def __buffer__(self, flags: int) -> memoryview:
        raise NotImplementedError("Cannot access ArrayBufferTransfer from Python")


if TYPE_CHECKING:
    AnyArrayBufferData: TypeAlias = (
        "AnyBuffer | JSArrayBuffer | JSSharedArrayBuffer | JSArrayBufferTransfer"
    )
    JSArrayBufferT = TypeVar(
        "JSArrayBufferT", bound=AnyArrayBufferData, default=AnyArrayBufferData
    )
else:
    JSArrayBufferT = TypeVar("JSArrayBufferT")


@frozen
class ByteOrder(Enum):
    Little = "little"
    Big = "big"


@frozen
class DataType(Enum):
    UnsignedInt = "integer", "bhilq"
    SignedInt = "integer", "BHILQ"
    Float = "float", "efd"
    Bytes = "bytes", "c"

    struct_formats: str

    def __new__(cls, name: str, struct_formats: str) -> Self:
        obj = object.__new__(cls)
        obj._value_ = name
        obj.struct_formats = struct_formats
        return obj


@dataclass(frozen=True, **slots_if310())
class DataFormat:
    byte_length: int
    data_type: DataType
    format: str

    @classmethod
    def resolve(cls, *, data_type: DataType, byte_length: int) -> Self:
        """Find the struct format on this platform with a given size and data type."""
        format: str | None = None
        for format in data_type.struct_formats:
            if struct.calcsize(format) == byte_length:
                break
        else:
            raise ValueError(
                f"DataType {data_type.name} has no struct_format of "
                f"byte_length {byte_length}"
            )
        return cls(data_type=data_type, format=format, byte_length=byte_length)


@dataclass(frozen=True, **slots_if310())
class JSArrayBufferView(Generic[JSArrayBufferT, AnyBufferT]):
    """A view to a range of a byte buffer.

    This constructor is more lenient than from_bytes() in that it does not
    require that the backing buffer is accessible and in-range. Views can be
    created out-of-range, in which case they are 0-length when accessed.

    Without this, view objects that enter an out-of-range state (due to the
    backing buffer resizing) would not be able to be copied, despite them
    already existing in the out-of-range state). Being out-of-range is not
    an error, rather an expected state that a view can be in.

    Use from_bytes() to enforce the creation behaviour of JavaScript
    TypedArray and DataView classes, which use aligned byte boundaries, and
    disallow creating currently-out-of-range views.
    """

    backing_buffer: JSArrayBufferT
    """The byte buffer this view exposes a range of."""
    item_offset: int = field(default=0)
    """The start of the view's backing_buffer range."""
    item_length: int | None = field(default=None)
    """The number of items in the view's backing_buffer range.

    None means the view's length dynamically changes if the buffer resizes.
    """
    readonly: Literal[True] | None = field(default=None)
    """Whether the view must be readonly.

    If None, the view is writable if the backing_buffer is.

    `readonly` MAY NOT be made writable using `True`, as the view reflects the
    readonly state of the backing_buffer.
    """

    view_tag: ClassVar[ArrayBufferViewTag]
    data_format: ClassVar[DataFormat]

    def __post_init__(self) -> None:
        if self.item_offset < 0:
            raise ValueError("item_offset cannot be negative")
        if self.item_length is not None and self.item_length < 0:
            raise ValueError("item_length cannot be negative")
        if self.readonly not in (True, None):
            raise ValueError("readonly must be True or None")

    @classmethod
    def from_bytes(
        cls,
        backing_buffer: JSArrayBufferT,
        *,
        view_tag: ArrayBufferViewTag = ArrayBufferViewTag.kUint8Array,
        byte_offset: int = 0,
        byte_length: int | None = None,
        readonly: Literal[True] | None = None,
    ) -> Self:
        itemsize = cls.data_format.byte_length

        if byte_offset % itemsize != 0:
            raise ItemSizeJSArrayBufferError(
                "byte_offset must be a multiple of the itemsize",
                itemsize=itemsize,
                byte_offset=byte_offset,
                byte_length=byte_length,
            )
        if byte_length is not None and byte_length % itemsize != 0:
            raise ItemSizeJSArrayBufferError(
                "byte_length must be a multiple of the itemsize",
                itemsize=itemsize,
                byte_offset=byte_offset,
                byte_length=byte_length,
            )

        item_offset = byte_offset // itemsize
        item_length = None if byte_length is None else byte_length // itemsize
        view = cls(
            backing_buffer,
            item_offset=item_offset,
            item_length=item_length,
            readonly=readonly,
        )

        try:
            # Access the buffer to find its byte length. The view will only be
            # able to report byte_offset and byte_length if the buffer is accessible
            with get_buffer(backing_buffer) as buf:
                msg = None
                if (  # Rather pedantic, but JavaScript enforces this.
                    byte_length is None
                    and not view.is_length_tracking
                    and buf.nbytes % itemsize != 0
                ):
                    msg = """backing_buffer byte length must be a multiple of \
the itemsize when the view does not have an explicit byte_length"""
                elif view.byte_offset < byte_offset:
                    msg = "byte_offset is not within the bounds of the backing_buffer"
                elif byte_length is not None and view.byte_length < byte_length:
                    msg = "byte_length is not within the bounds of the backing_buffer"
                if msg:
                    raise BoundsJSArrayBufferError(
                        msg,
                        byte_offset=byte_offset,
                        byte_length=byte_length,
                        buffer_byte_length=buf.nbytes,
                    )
        except NotImplementedError:
            # Can't access some backing buffers — they may raise
            # NotImplementedError. For example, JSSharedArrayBuffer and
            # JSArrayBufferTransfer. In these cases we allow the view to be
            # created, as failing would prevent deserialization of other
            # objects. In practice I don't think these shared buffers will occur
            # in real serialized data.
            pass
        return view

    @property
    def byte_offset(self) -> int:
        """The view's position in the backing_buffer.

        The offset is 0 when the buffer is out-of-range, or the number of bytes
        given by `item_offset * view_format.itemsize`.
        """
        if not self.is_in_range:
            return 0
        return self.item_offset * self.data_format.byte_length

    @property
    def byte_length(self) -> int:
        return self.__get_buffer_as_memoryview()[1].nbytes

    @property
    def is_length_tracking(self) -> bool:
        return self.item_length is None and self.is_backing_buffer_resizable

    @property
    def is_backing_buffer_resizable(self) -> bool:
        bb = self.backing_buffer
        return isinstance(bb, bytearray) or (
            isinstance(bb, JSArrayBuffer) and bb.resizable
        )

    @property
    def is_in_range(self) -> bool:
        return self.__get_buffer_as_memoryview()[0]

    @abstractmethod
    def get_buffer(
        self, *, readonly: Literal[True] | None = None
    ) -> ContextManager[AnyBufferT]: ...

    def __get_buffer_as_memoryview(
        self, *, readonly: Literal[True] | None = None
    ) -> tuple[bool, memoryview]:
        try:
            mv = get_buffer(self.backing_buffer)
        except NotImplementedError:
            mv = memoryview(b"")
        if mv.itemsize != 1 or mv.ndim != 1:
            mv = mv.cast("c")  # 1-dimensional bytes
        if self.readonly or readonly:
            mv = mv.toreadonly()

        itemsize = self.data_format.byte_length
        item_length = self.item_length

        byte_offset = self.item_offset * itemsize
        byte_length = None if item_length is None else item_length * itemsize
        in_range = byte_offset <= mv.nbytes

        if byte_length is not None:
            # When out-of-range, the view becomes empty
            if byte_offset + byte_length > mv.nbytes:
                byte_length = 0
                in_range = False
            mv = mv[byte_offset : byte_offset + byte_length]
            assert len(mv) == byte_length
        else:
            if byte_offset > mv.nbytes:
                byte_length = 0
                in_range = False
            # Variable length buffers adjust their length to the largest
            # multiple of itemsize within the bounds.
            available_bytes = max(0, mv.nbytes - byte_offset)
            full_items, partial_items = divmod(available_bytes, itemsize)
            current_byte_length = full_items * itemsize
            mv = mv[byte_offset : byte_offset + current_byte_length]

        return in_range, mv

    def get_buffer_as_memoryview(
        self, *, readonly: Literal[True] | None = None
    ) -> memoryview:
        return self.__get_buffer_as_memoryview(readonly=readonly)[1]

    def __eq__(self, value: object) -> bool:
        if self is value:
            return True
        if isinstance(value, JSArrayBufferView):
            value = cast("JSArrayBufferView[AnyArrayBufferData, AnyBufferT]", value)
            try:
                with (
                    self.get_buffer(readonly=True) as self_data,
                    value.get_buffer(readonly=True) as value_data,
                ):
                    return self_data == value_data
            except NotImplementedError:
                pass
        return NotImplemented

    def __hash__(self) -> int:
        try:
            with self.get_buffer_as_memoryview(readonly=True) as data:
                # data may not be hashable, depending on backing buffer
                return hash(data)
        except NotImplementedError:
            raise TypeError(
                f"cannot hash {type(self).__name__} with inaccessible buffer"
            )

    def __repr__(self) -> str:
        arg_pieces = [
            f"{self.backing_buffer!r}",
            None if self.item_offset == 0 else f"item_offset={self.item_offset!r}",
            None if self.item_length is None else f"item_length={self.item_length!r}",
            None if self.readonly is None else f"readonly={self.item_length!r}",
        ]
        args = ", ".join(a for a in arg_pieces if a)
        return f"{type(self).__name__}({args})"


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
    ElementT = TypeVar("ElementT", bound="int | float", default="int | float")
else:
    ViewTagT = TypeVar("ViewTagT")
    ElementT = TypeVar("ElementT")


class JSTypedArray(
    JSArrayBufferView[JSArrayBufferT, memoryview],
    AnyArrayBufferView,
    Generic[JSArrayBufferT, ViewTagT],
):
    element_type: ClassVar[type[int] | type[float]]

    # FIXME: memoryview is generic in typeshed, but mypy errors if I give it the
    #  ElementT annotation (should match cls.element_type)
    def get_buffer(
        self, *, readonly: Literal[True] | None = None
    ) -> ContextManager[memoryview]:
        return self.get_buffer_as_memoryview(readonly=readonly).cast(
            self.data_format.format
        )


class JSInt8Array(JSTypedArray[JSArrayBufferT, Literal[ArrayBufferViewTag.kInt8Array]]):
    element_type = int
    view_tag = ArrayBufferViewTag.kInt8Array
    data_format = DataFormat.resolve(data_type=DataType.SignedInt, byte_length=1)


class JSUint8Array(
    JSTypedArray[JSArrayBufferT, Literal[ArrayBufferViewTag.kUint8Array]]
):
    element_type = int
    view_tag = ArrayBufferViewTag.kUint8Array
    data_format = DataFormat.resolve(data_type=DataType.UnsignedInt, byte_length=1)


class JSUint8ClampedArray(
    JSTypedArray[JSArrayBufferT, Literal[ArrayBufferViewTag.kUint8ClampedArray]]
):
    element_type = int
    view_tag = ArrayBufferViewTag.kUint8ClampedArray
    data_format = DataFormat.resolve(data_type=DataType.UnsignedInt, byte_length=1)


class JSInt16Array(
    JSTypedArray[JSArrayBufferT, Literal[ArrayBufferViewTag.kInt16Array]]
):
    element_type = int
    view_tag = ArrayBufferViewTag.kInt16Array
    data_format = DataFormat.resolve(data_type=DataType.SignedInt, byte_length=2)


class JSUint16Array(
    JSTypedArray[JSArrayBufferT, Literal[ArrayBufferViewTag.kUint16Array]]
):
    element_type = int
    view_tag = ArrayBufferViewTag.kUint16Array
    data_format = DataFormat.resolve(data_type=DataType.UnsignedInt, byte_length=2)


class JSInt32Array(
    JSTypedArray[JSArrayBufferT, Literal[ArrayBufferViewTag.kInt32Array]]
):
    element_type = int
    view_tag = ArrayBufferViewTag.kInt32Array
    data_format = DataFormat.resolve(data_type=DataType.SignedInt, byte_length=4)


class JSUint32Array(
    JSTypedArray[JSArrayBufferT, Literal[ArrayBufferViewTag.kUint32Array]]
):
    element_type = int
    view_tag = ArrayBufferViewTag.kUint32Array
    data_format = DataFormat.resolve(data_type=DataType.UnsignedInt, byte_length=4)


class JSFloat16Array(
    JSTypedArray[JSArrayBufferT, Literal[ArrayBufferViewTag.kFloat16Array]]
):
    element_type = float
    view_tag = ArrayBufferViewTag.kFloat16Array
    data_format = DataFormat.resolve(data_type=DataType.Float, byte_length=2)


class JSFloat32Array(
    JSTypedArray[JSArrayBufferT, Literal[ArrayBufferViewTag.kFloat32Array]]
):
    element_type = float
    view_tag = ArrayBufferViewTag.kFloat32Array
    data_format = DataFormat.resolve(data_type=DataType.Float, byte_length=4)


class JSFloat64Array(
    JSTypedArray[JSArrayBufferT, Literal[ArrayBufferViewTag.kFloat64Array]]
):
    element_type = float
    view_tag = ArrayBufferViewTag.kFloat64Array
    data_format = DataFormat.resolve(data_type=DataType.Float, byte_length=8)


class JSBigInt64Array(
    JSTypedArray[JSArrayBufferT, Literal[ArrayBufferViewTag.kBigInt64Array]]
):
    element_type = int
    view_tag = ArrayBufferViewTag.kBigInt64Array
    data_format = DataFormat.resolve(data_type=DataType.SignedInt, byte_length=8)


class JSBigUint64Array(
    JSTypedArray[JSArrayBufferT, Literal[ArrayBufferViewTag.kBigUint64Array]]
):
    element_type = int
    view_tag = ArrayBufferViewTag.kBigUint64Array
    data_format = DataFormat.resolve(data_type=DataType.UnsignedInt, byte_length=8)


class BackportJSFloat16Array(JSFloat16Array):
    """An alternate implementation of `JSFloat16Array` that supports Python < 3.12.

    Python versions before 3.12 don't support 16-bit floats as a memoryview format.
    This implementation copies 16-bit floats to/from a 32-bit float array when
    get_buffer() accesses the array.
    """

    @contextmanager
    def get_buffer(
        self, *, readonly: Literal[True] | None = None
    ) -> Generator[memoryview]:
        with self.get_buffer_as_memoryview(readonly=readonly) as buffer:
            assert buffer.ndim == 1
            assert buffer.itemsize == 1
            assert buffer.format == "B"
            length, remainder = divmod(len(buffer), 2)
            assert remainder == 0
            data = bytearray(length * 4)
            view = memoryview(data).cast("f")
            assert len(view) * 2 == len(buffer)

            half_float = struct.Struct("e")
            for i, v in enumerate(half_float.iter_unpack(buffer)):
                view[i] = v[0]

            yield view.toreadonly() if buffer.readonly else view

            # skip write back if the view was released
            try:
                view.obj  # will raise if view.release() was called
            except ValueError:
                return

            if buffer.readonly:
                return

            for i, fv in enumerate(view):
                half_float.pack_into(buffer, i * 2, fv)


# Use BackportJSFloat16Array in place of JSFloat16Array in Python versions that
# can't use half floats in memoryview.
MemoryviewJSFloat16Array: type[JSFloat16Array] = JSFloat16Array
try:
    memoryview(b"").cast("e")
except ValueError:
    JSFloat16Array = BackportJSFloat16Array  # type: ignore[misc, assignment]


@dataclass(frozen=True)
class DataViewBuffer(AbstractContextManager["DataViewBuffer"]):
    buffer: memoryview

    def __buffer__(self, flags: int | BufferFlags) -> memoryview:
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
    view_tag = ArrayBufferViewTag.kDataView
    data_format = DataFormat.resolve(data_type=DataType.Bytes, byte_length=1)

    def get_buffer(self, *, readonly: Literal[True] | None = None) -> DataViewBuffer:
        return DataViewBuffer(self.get_buffer_as_memoryview(readonly=readonly))


@dataclass(unsafe_hash=True, order=True, **slots_if310())
class ViewFormat:
    view_tag: ArrayBufferViewTag
    view_type: type[JSTypedArray] | type[JSDataView]


@frozen
class ArrayBufferViewStructFormat(ViewFormat, Enum):
    Int8Array = ArrayBufferViewTag.kInt8Array, JSInt8Array
    Uint8Array = ArrayBufferViewTag.kUint8Array, JSUint8Array
    # Python doesn't distinguish between wrapping and clamped views, because
    # setting out-of-range values throws an error.
    Uint8ClampedArray = ArrayBufferViewTag.kUint8ClampedArray, JSUint8ClampedArray
    Int16Array = ArrayBufferViewTag.kInt16Array, JSInt16Array
    Uint16Array = ArrayBufferViewTag.kUint16Array, JSUint16Array
    Int32Array = ArrayBufferViewTag.kInt32Array, JSInt32Array
    Uint32Array = ArrayBufferViewTag.kUint32Array, JSUint32Array
    Float16Array = ArrayBufferViewTag.kFloat16Array, JSFloat16Array
    Float32Array = ArrayBufferViewTag.kFloat32Array, JSFloat32Array
    Float64Array = ArrayBufferViewTag.kFloat64Array, JSFloat64Array
    BigInt64Array = ArrayBufferViewTag.kBigInt64Array, JSBigInt64Array
    BigUint64Array = ArrayBufferViewTag.kBigUint64Array, JSBigUint64Array
    # DataView doesn't have a single format, we use bytes format as a default.
    # As in accessing the buffer provides actual bytes objects, not integers.
    DataView = ArrayBufferViewTag.kDataView, JSDataView

    @staticmethod
    @functools.lru_cache  # noqa: B019 # OK because static method
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
    readonly: Literal[True] | None = None,
) -> JSTypedArray | JSDataView:
    if isinstance(format, ArrayBufferViewTag):
        format = ArrayBufferViewStructFormat(format)
    return format.view_type.from_bytes(
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
    byte_offset: int
    byte_length: int | None

    def __init__(
        self, message: str, *, itemsize: int, byte_offset: int, byte_length: int | None
    ) -> None:
        super(ItemSizeJSArrayBufferError, self).__init__(message)
        self.itemsize = itemsize
        self.byte_offset = byte_offset
        self.byte_length = byte_length


@dataclass(init=False)
class BoundsJSArrayBufferError(JSArrayBufferError, ValueError):
    byte_offset: int
    byte_length: int | None
    buffer_byte_length: int

    def __init__(
        self,
        message: str,
        byte_offset: int,
        byte_length: int | None,
        buffer_byte_length: int,
    ):
        super(BoundsJSArrayBufferError, self).__init__(message)
        self.byte_offset = byte_offset
        self.byte_length = byte_length
        self.buffer_byte_length = buffer_byte_length
