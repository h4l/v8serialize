from __future__ import annotations

import functools
import struct
from abc import ABC, abstractmethod
from collections.abc import Sized
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
from v8serialize._errors import V8SerializeError
from v8serialize._pycompat.inspect import BufferFlags
from v8serialize._pycompat.typing import ReadableBinary, get_buffer
from v8serialize._values import (
    AnyArrayBuffer,
    AnyArrayBufferTransfer,
    AnyArrayBufferView,
    AnySharedArrayBuffer,
    SharedArrayBufferId,
    TransferId,
)
from v8serialize.constants import ArrayBufferViewTag
from v8serialize.jstypes import _repr

if TYPE_CHECKING:
    from typing_extensions import Buffer, Self, TypeAlias, TypeVar

    AnyBuffer: TypeAlias = "ReadableBinary | Buffer"
    AnyBufferT_co = TypeVar(
        "AnyBufferT_co", bound=AnyBuffer, default=AnyBuffer, covariant=True
    )
    BufferT_co = TypeVar(
        "BufferT_co", bound=ReadableBinary, default=ReadableBinary, covariant=True
    )
else:
    from typing import TypeVar

    AnyBufferT_co = TypeVar("AnyBufferT_co")
    BufferT_co = TypeVar("BufferT_co", covariant=True)


@dataclass(frozen=True, slots=True)
class BaseJSArrayBuffer(ABC):
    @abstractmethod
    def __buffer__(self, flags: int) -> memoryview: ...


@BaseJSArrayBuffer.register
@dataclass(frozen=True, init=False, slots=True)
class JSArrayBuffer(
    AnyArrayBuffer,
    AbstractContextManager["JSArrayBuffer[BufferT_co]"],
    ABC,
    Generic[BufferT_co],
):
    """
    Python equivalent of [JavaScript's ArrayBuffer][ArrayBuffer].

    * This is a [context manager] which returns itself and calls `close()` on exit.
    * This is a [Buffer] which exposes its `data` as a memoryview.

    [ArrayBuffer]: https://developer.mozilla.org/en-US/docs/Web/JavaScript/\
Reference/Global_Objects/ArrayBuffer
    [context manager]: (`typecontextmanager`)
    [Buffer]: (`collections.abc.Buffer`)

    Parameters
    ----------
    data
        Binary data to populate the buffer with. Default: null bytes of
        `byte_length`.
    byte_length
        The number of bytes the buffer will be created with. Default: length of
        `data` or 0.
    max_byte_length
        The maximum length the buffer can be resized to. The buffer will not be
        resizable if this isn't set. Default: the initial length of the buffer.
    resizable
        Make the buffer resizable, starting at its maximum length. Default:
        `True` if a `max_byte_length` is set.
    copy_data
        Whether to copy the `data` parameter, or wrap it as is. Default: `True`.
    readonly
        Whether to allow the buffer data to be modified. Default: `False`
    """

    _data: BufferT_co  # type: ignore[misc,unused-ignore]
    max_byte_length: int
    """The maximum size that `resize()` can expand this buffer to."""
    resizable: bool
    """Whether this buffer can be resized with `resize()`."""

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
        readonly = False if readonly is None else readonly

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
        """Resize the buffer, within the `max_byte_length` limit."""
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
        """The buffer's binary data."""
        return self.__buffer__(BufferFlags.SIMPLE)

    def __enter__(self) -> JSArrayBuffer[BufferT_co]:
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
        """Release the buffer's data if it's a [`memoryview`](`typememoryview`)."""
        if isinstance(self._data, memoryview):
            self._data.release()

    def __buffer__(self, flags: int | BufferFlags) -> memoryview:
        return get_buffer(self._data, flags)[: self.max_byte_length]

    def __repr__(self) -> str:
        return _repr.js_repr(self)


@BaseJSArrayBuffer.register
@dataclass(frozen=True, slots=True)
class JSSharedArrayBuffer(AnySharedArrayBuffer, ABC):
    """
    Python equivalent of [JavaScript's SharedArrayBuffer].

    This type exists for completeness, and to allow these values to be
    round-tripped back to V8 if they ever do occur.

    Much like [`JSArrayBufferTransfer`], this type should not occur in practice.
    It currently does nothing other than hold an integer `buffer_id`. V8 does
    not seem to allow SharedArrayBuffer objects to be serialized by Node.JS's
    [`v8.serialize()`] API.

    [JavaScript's SharedArrayBuffer]: https://developer.mozilla.org/en-US/docs\
/Web/JavaScript/Reference/Global_Objects/SharedArrayBuffer
    [`JSArrayBufferTransfer`]: `v8serialize.jstypes.JSArrayBufferTransfer`
    [`v8.serialize()`]: https://nodejs.org/api/v8.html#serialization-api
    """

    buffer_id: SharedArrayBufferId

    def __buffer__(self, flags: int) -> memoryview:
        raise NotImplementedError("Cannot access SharedArrayBuffer from Python")


@BaseJSArrayBuffer.register
@dataclass(frozen=True, slots=True)
class JSArrayBufferTransfer(AnyArrayBufferTransfer, ABC):
    """A non-standard V8 type representing an ArrayBuffer being [transferred].

    This type exists for completeness, but should not occur in data serialized
    by JavaScript runtimes using APIs like Node.JS's [`v8.serialize()`].
    Transferring ArrayBuffers is an internal activity in V8 and it's not
    possible to access this type from JavaScript code running in V8, so it can't
    be serialized from JavaScript code.

    [transferred]: https://developer.mozilla.org/en-US/docs/Web/JavaScript/\
Reference/Global_Objects/ArrayBuffer#transferring_arraybuffers
    [`v8.serialize()`]: https://nodejs.org/api/v8.html#serialization-api
    """

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
    JSArrayBufferT_co = TypeVar(
        "JSArrayBufferT_co",
        bound=AnyArrayBufferData,
        default=AnyArrayBufferData,
        covariant=True,
    )
else:
    JSArrayBufferT = TypeVar("JSArrayBufferT")
    JSArrayBufferT_co = TypeVar("JSArrayBufferT_co")


@frozen
class ByteOrder(Enum):
    Little = "little"
    Big = "big"


@frozen
class DataType(Enum):
    """An enum of the data types used in JavaScript buffers."""

    UnsignedInt = int, "BHILQ"
    SignedInt = int, "bhilq"
    Float = float, "efd"
    Bytes = bytes, "c"

    python_type: type[int | float | bytes]
    """The Python type that represents this data type."""
    struct_formats: str
    """The struct module format characters for this `DataType`."""

    def __new__(
        cls, python_type: type[int | float | bytes], struct_formats: str
    ) -> Self:
        obj = object.__new__(cls)
        obj._value_ = (python_type, struct_formats)
        obj.python_type = python_type
        obj.struct_formats = struct_formats
        return obj

    @overload
    def cast(  # type: ignore[misc]
        self: Literal[DataType.UnsignedInt, DataType.SignedInt],
        view: memoryview,
        *,
        data_format: DataFormat,
    ) -> memoryview[int]: ...

    @overload
    def cast(  # type: ignore[misc]
        self: Literal[DataType.Float],
        view: memoryview,
        *,
        data_format: DataFormat,
    ) -> memoryview[float]: ...

    @overload
    def cast(  # type: ignore[misc]
        self: Literal[DataType.Bytes],
        view: memoryview,
        *,
        data_format: DataFormat,
    ) -> memoryview[bytes]: ...

    def cast(
        self, view: memoryview, *, data_format: DataFormat
    ) -> memoryview[int] | memoryview[float] | memoryview[bytes]:
        if data_format.data_type is not self:
            raise TypeError(
                "data_format.data_type must be the DataType cast() is called on"
            )
        assert data_format.format in self.struct_formats
        format = cast(Literal["c", "f", "b"], data_format.format)
        return view.cast(format)

    def __repr__(self) -> str:
        return f"{type(self).__name__}.{self._name_}"


AnyDataType = Literal[
    DataType.UnsignedInt, DataType.SignedInt, DataType.Float, DataType.Bytes
]


@dataclass(frozen=True, slots=True)
class DataFormat:
    """A [struct format] for a specific data type and precision.

    [struct format]: `struct`
    """

    byte_length: int
    data_type: AnyDataType
    format: str

    @classmethod
    def resolve(cls, *, data_type: AnyDataType, byte_length: int) -> Self:
        """
        Find the struct format on this platform with a given size and data type.

        Parameters
        ----------
        data_type
            The data type to resolve.
        byte_length
            The required precision in bytes ($bits/8$, e.g. 32 bits is 4 bytes).

        Returns
        -------
        A `DataFormat` matching the parameters.

        Raises
        ------
        ValueError
            If the platform does not support a data type with the requested parameters.

        Examples
        --------
        >>> DataFormat.resolve(data_type=DataType.UnsignedInt, byte_length=4)
        DataFormat(byte_length=4, data_type=DataType.UnsignedInt, format='I')
        """  # noqa: E501
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

    def cast(
        self, view: memoryview[Any]
    ) -> memoryview[int] | memoryview[float] | memoryview[bytes]:
        return self.data_type.cast(view, data_format=self)


@dataclass(frozen=True, slots=True)
class JSArrayBufferView(Generic[JSArrayBufferT_co, AnyBufferT_co]):
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

    backing_buffer: JSArrayBufferT_co  # type: ignore[misc,unused-ignore]
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
    """The [`ArrayBufferViewTag`](`v8serialize.constants.ArrayBufferViewTag`) this view is for."""  # noqa: E501
    data_format: ClassVar[DataFormat]
    """
    The [`DataFormat`](`v8serialize.jstypes.DataFormat`) for this view's data type.
    """

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
        byte_offset: int = 0,
        byte_length: int | None = None,
        readonly: Literal[True] | None = None,
    ) -> Self:
        """
        Create a view, validating byte offsets as JavaScript does.

        See Also
        --------
        [`create_view()`](`v8serialize.jstypes.create_view`)
        : Create a view without specifying the view class.
        """
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
            backing_buffer,  # type: ignore[arg-type]
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
        """The number of bytes accessible through this view."""
        return self.__get_buffer_as_memoryview()[1].nbytes

    @property
    def is_length_tracking(self) -> bool:
        """Whether this view changes length to match a resizable `.backing_buffer`."""
        return self.item_length is None and self.is_backing_buffer_resizable

    @property
    def is_backing_buffer_resizable(self) -> bool:
        """Whether `.backing_buffer` can change its byte length."""
        bb = self.backing_buffer
        return isinstance(bb, bytearray) or (
            isinstance(bb, JSArrayBuffer) and bb.resizable
        )

    @property
    def is_in_range(self) -> bool:
        """Whether this view's entire range exists in the `.backing_buffer`."""
        return self.__get_buffer_as_memoryview()[0]

    @abstractmethod
    def get_buffer(
        self, *, readonly: Literal[True] | None = None
    ) -> ContextManager[AnyBufferT_co]: ...

    def __get_buffer_as_memoryview(
        self, *, readonly: Literal[True] | None = None
    ) -> tuple[bool, memoryview]:
        try:
            mv = get_buffer(self.backing_buffer)
        except NotImplementedError:
            mv = memoryview(b"")
        # get_buffer() guarantees this
        assert mv.itemsize == 1 and mv.ndim == 1 and mv.format == "B"
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
        """
        Access the view's region of `.backing_buffer` as a `memoryview`.

        The returned `memoryview`:

        * Will be **empty** if the view is not in range.
        * Is always 1-dimensional and contains uint8 items (format `"B"`).

        Parameters
        ----------
        readonly
            If True, the returned `memoryview` will be read-only (even if this
            view itself is not read-only).
        """
        return self.__get_buffer_as_memoryview(readonly=readonly)[1]

    def __eq__(self, value: object) -> bool:
        if self is value:
            return True
        if isinstance(value, JSArrayBufferView):
            value = cast("JSArrayBufferView[AnyArrayBufferData, AnyBufferT_co]", value)
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
        except NotImplementedError as e:
            raise TypeError(
                f"cannot hash {type(self).__name__} with inaccessible buffer"
            ) from e

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
    ViewTagT_co = TypeVar(
        "ViewTagT_co", bound=TypedViewTag, default=TypedViewTag, covariant=True
    )
    ElementT = TypeVar("ElementT", bound="int | float", default="int | float")
else:
    ViewTagT_co = TypeVar("ViewTagT_co")
    ElementT = TypeVar("ElementT")


class JSTypedArray(
    JSArrayBufferView[JSArrayBufferT_co, "memoryview[Any]"],
    AnyArrayBufferView,
    Generic[JSArrayBufferT_co, ViewTagT_co],
):
    """
    Python equivalent of [JavaScript's TypedArray].

    :::{.callout-note}
    As in JavaScript, this is an abstract type which cannot be instantiated.
    :::

    [JavaScript's TypedArray]: https://developer.mozilla.org/en-US/docs/Web/\
JavaScript/Reference/Global_Objects/TypedArray

    See Also
    --------
    [`create_view()`](`v8serialize.jstypes.create_view`)
    : Create a (subtype) instance of `JSTypedArray`.

    `JS*Array` types
    : This module contains many subtypes for specific data formats, e.g. \
[`JSUint8Array`](`v8serialize.jstypes.JSUint8Array`).
    """

    element_type: ClassVar[type[int | float]]
    """The Python type of this view's individual indexes."""

    # FIXME: should be possible to make the memoryview's generic element type
    #        carry through from the instance's DataFormat. Is it worth all the
    #        hoop-jumping though? Might just be painful for client code to
    #        annotate their use correctly.
    def get_buffer(
        self, *, readonly: Literal[True] | None = None
    ) -> ContextManager[memoryview[Any]]:
        r"""
        Get a context manager that provides this view's region as a `memoryview`.

        Examples
        --------
        >>> with JSUint8Array.from_bytes(b'\xFF\x80').get_buffer() as mv:
        ...     assert isinstance(mv, memoryview)
        ...     print(mv[0], mv[1])
        255 128
        """
        return self.data_format.cast(self.get_buffer_as_memoryview(readonly=readonly))


class JSInt8Array(
    JSTypedArray[JSArrayBufferT_co, Literal[ArrayBufferViewTag.kInt8Array]]
):
    element_type = int
    view_tag = ArrayBufferViewTag.kInt8Array
    data_format = DataFormat.resolve(data_type=DataType.SignedInt, byte_length=1)


class JSUint8Array(
    JSTypedArray[JSArrayBufferT_co, Literal[ArrayBufferViewTag.kUint8Array]]
):
    element_type = int
    view_tag = ArrayBufferViewTag.kUint8Array
    data_format = DataFormat.resolve(data_type=DataType.UnsignedInt, byte_length=1)


class JSUint8ClampedArray(
    JSTypedArray[JSArrayBufferT_co, Literal[ArrayBufferViewTag.kUint8ClampedArray]]
):
    element_type = int
    view_tag = ArrayBufferViewTag.kUint8ClampedArray
    data_format = DataFormat.resolve(data_type=DataType.UnsignedInt, byte_length=1)


class JSInt16Array(
    JSTypedArray[JSArrayBufferT_co, Literal[ArrayBufferViewTag.kInt16Array]]
):
    element_type = int
    view_tag = ArrayBufferViewTag.kInt16Array
    data_format = DataFormat.resolve(data_type=DataType.SignedInt, byte_length=2)


class JSUint16Array(
    JSTypedArray[JSArrayBufferT_co, Literal[ArrayBufferViewTag.kUint16Array]]
):
    element_type = int
    view_tag = ArrayBufferViewTag.kUint16Array
    data_format = DataFormat.resolve(data_type=DataType.UnsignedInt, byte_length=2)


class JSInt32Array(
    JSTypedArray[JSArrayBufferT_co, Literal[ArrayBufferViewTag.kInt32Array]]
):
    element_type = int
    view_tag = ArrayBufferViewTag.kInt32Array
    data_format = DataFormat.resolve(data_type=DataType.SignedInt, byte_length=4)


class JSUint32Array(
    JSTypedArray[JSArrayBufferT_co, Literal[ArrayBufferViewTag.kUint32Array]]
):
    element_type = int
    view_tag = ArrayBufferViewTag.kUint32Array
    data_format = DataFormat.resolve(data_type=DataType.UnsignedInt, byte_length=4)


class JSFloat16Array(
    JSTypedArray[JSArrayBufferT_co, Literal[ArrayBufferViewTag.kFloat16Array]]
):
    element_type = float
    view_tag = ArrayBufferViewTag.kFloat16Array
    data_format = DataFormat.resolve(data_type=DataType.Float, byte_length=2)


class JSFloat32Array(
    JSTypedArray[JSArrayBufferT_co, Literal[ArrayBufferViewTag.kFloat32Array]]
):
    element_type = float
    view_tag = ArrayBufferViewTag.kFloat32Array
    data_format = DataFormat.resolve(data_type=DataType.Float, byte_length=4)


class JSFloat64Array(
    JSTypedArray[JSArrayBufferT_co, Literal[ArrayBufferViewTag.kFloat64Array]]
):
    element_type = float
    view_tag = ArrayBufferViewTag.kFloat64Array
    data_format = DataFormat.resolve(data_type=DataType.Float, byte_length=8)


class JSBigInt64Array(
    JSTypedArray[JSArrayBufferT_co, Literal[ArrayBufferViewTag.kBigInt64Array]]
):
    element_type = int
    view_tag = ArrayBufferViewTag.kBigInt64Array
    data_format = DataFormat.resolve(data_type=DataType.SignedInt, byte_length=8)


class JSBigUint64Array(
    JSTypedArray[JSArrayBufferT_co, Literal[ArrayBufferViewTag.kBigUint64Array]]
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
    ) -> Generator[memoryview[Any]]:
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
                view.obj  # noqa: B018  # will raise if view.release() was called
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
    # annotations don't know about the 'e' float16 format
    memoryview(b"").cast(cast(Literal["f"], "e"))
except ValueError:
    JSFloat16Array = BackportJSFloat16Array  # type: ignore[misc, assignment]


@dataclass(frozen=True)
class DataViewBuffer(AbstractContextManager["DataViewBuffer"]):
    """
    Provides methods to read/write data types in a [`JSDataView`].

    This is return type of [`JSDataView.get_buffer()`]. It provides all the
    methods to read/write binary data as variable-width int/float data types
    that [JavaScript's DataView] provides.

    * This is a [context manager] which returns itself and releases `.buffer` on exit.
    * This is a [Buffer] which exposes its `.buffer` as a memoryview.

    :::{.callout-note}
    The `get_*`/`set_*` methods read & write values as big-endian unless the
    `little_endian=True` argument is used. Most computers are have little-endian
    native byte order, and the V8 serialization format itself is defined as
    using the system's native byte order, and `v8serialize` assumes it's running
    on a little-endian system.
    :::

    [`JSDataView`]: `v8serialize.jstypes.JSDataView`
    [`JSDataView.get_buffer()`]: `v8serialize.jstypes.JSDataView.get_buffer`
    [JavaScript's DataView]: https://developer.mozilla.org/en-US/docs/Web/\
JavaScript/Reference/Global_Objects/DataView

    See Also
    --------
    [Python's `struct` module](`struct`)
    : This is the builtin way to read/write binary data with Python.

    [NumPy Structured Arrays](https://numpy.org/doc/stable/user/basics.rec.html)
    : NumPy provides Structured Arrays which can read/write structured binary \
data in bulk.
    """

    buffer: memoryview
    """The `memoryview` this view is operating on."""

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
        return self.read("<H" if little_endian else ">H", byte_offset)[0]  # type: ignore[no-any-return]

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


class JSDataView(JSArrayBufferView[JSArrayBufferT_co, DataViewBuffer]):
    r"""
    Python equivalent of [JavaScript's DataView].

    [JavaScript's DataView]: https://developer.mozilla.org/en-US/docs/Web/\
JavaScript/Reference/Global_Objects/DataView

    Examples
    --------
    >>> dv = JSDataView(bytearray(3))
    >>> with dv.get_buffer() as buf:
    ...     buf.set_uint8(0, 1)
    ...     buf.set_uint8(1, 2)
    ...     print("256 + 2 =", buf.get_uint16(0))  # big-endian by default
    ...     print("256 * 2 + 1 =", buf.get_uint16(0, little_endian=True))
    256 + 2 = 258
    256 * 2 + 1 = 513
    >>> dv.backing_buffer
    bytearray(b'\x01\x02\x00')
    """

    view_tag = ArrayBufferViewTag.kDataView
    data_format = DataFormat.resolve(data_type=DataType.Bytes, byte_length=1)

    def get_buffer(self, *, readonly: Literal[True] | None = None) -> DataViewBuffer:
        """
        Access the view's region of `.backing_buffer` as a [`DataViewBuffer`].

        [`DataViewBuffer`]: `v8serialize.jstypes.DataViewBuffer`
        """
        return DataViewBuffer(self.get_buffer_as_memoryview(readonly=readonly))


@dataclass(unsafe_hash=True, order=True, slots=True)
class ViewFormat:
    view_tag: ArrayBufferViewTag
    view_type: type[JSTypedArray | JSDataView]


@frozen
class ArrayBufferViewStructFormat(ViewFormat, Enum):
    """
    An enum of the TypedArray and DataView types.

    This is used to name view types, and resolve the view type for an
    [`ArrayBufferViewTag`](`v8serialize.constants.ArrayBufferViewTag`) value.

    Examples
    --------
    >>> from v8serialize.constants import ArrayBufferViewTag

    Resolve a view type from a `ArrayBufferViewTag`:

    >>> ArrayBufferViewStructFormat(ArrayBufferViewTag.kUint32Array).view_type
    <class 'v8serialize.jstypes.jsbuffers.JSUint32Array'>

    Resolve a view type from data type and precision:

    >>> uint64 = DataFormat.resolve(data_type=DataType.UnsignedInt, byte_length=8)
    >>> ArrayBufferViewStructFormat(uint64).view_type
    <class 'v8serialize.jstypes.jsbuffers.JSBigUint64Array'>
    """

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
            if value.view_tag is arg or value.view_type.data_format == arg:
                return value
        return None

    if TYPE_CHECKING:

        def __init__(
            self, value: ArrayBufferViewTag | DataFormat | ArrayBufferViewStructFormat
        ) -> None: ...


def create_view(
    buffer: JSArrayBufferT,
    format: ArrayBufferViewTag | DataFormat | ArrayBufferViewStructFormat,
    *,
    byte_offset: int = 0,
    byte_length: int | None = None,
    readonly: Literal[True] | None = None,
) -> JSTypedArray | JSDataView:
    r"""
    Create a view over a data buffer, enforcing byte boundaries as JavaScript does.

    This creates an instance of the appropriate view type for the `format`.

    Returns
    -------
    DataView | TypedArray:
        An instance of `DataView` or `TypedArray` wrapping `buffer`.

    Examples
    --------
    >>> from v8serialize.constants import ArrayBufferViewTag
    >>> create_view(b'', format=ArrayBufferViewTag.kUint32Array)
    JSUint32Array(b'')

    >>> uint64 = DataFormat.resolve(data_type=DataType.UnsignedInt, byte_length=8)
    >>> create_view(b'', format=uint64)
    JSBigUint64Array(b'')
    """
    if isinstance(format, (ArrayBufferViewTag, DataFormat)):
        format = ArrayBufferViewStructFormat(format)
    return format.view_type.from_bytes(
        buffer,
        byte_offset=byte_offset,
        byte_length=byte_length,
        readonly=readonly,
    )


@dataclass(init=False)
class JSArrayBufferError(V8SerializeError):
    """The parent type of exceptions raised by the JavaScript buffer types."""

    pass


@dataclass(init=False)
class ByteLengthJSArrayBufferError(V8SerializeError, ValueError):
    """Raised when a byte length is out of bounds."""

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
    """Raised when a byte offset or length is not divisible by itemsize."""

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
    """Raised when a byte offset is out of bounds."""

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
