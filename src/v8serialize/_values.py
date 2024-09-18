from __future__ import annotations

from typing import (
    TYPE_CHECKING,
    Literal,
    NewType,
    Protocol,
    TypeVar,
    overload,
    runtime_checkable,
)

from v8serialize._pycompat.typing import ReadableBinary
from v8serialize.constants import ArrayBufferViewTag, JSErrorName

if TYPE_CHECKING:
    from typing_extensions import TypeAlias

T_co = TypeVar("T_co", covariant=True)

SharedArrayBufferId = NewType("SharedArrayBufferId", int)
TransferId = NewType("TransferId", int)


@runtime_checkable
class AnyArrayBuffer(Protocol):
    """
    A Protocol matching [JSArrayBuffer].

    [JSArrayBuffer]: `v8serialize.jstypes.JSArrayBuffer`
    """

    if TYPE_CHECKING:

        @property
        def data(self) -> ReadableBinary: ...
        @property
        def max_byte_length(self) -> int: ...
        @property
        def resizable(self) -> bool: ...

    else:
        # test/test_protocol_dataclass_interaction.py
        data = ...
        max_byte_length = ...
        resizable = ...


@runtime_checkable
class AnySharedArrayBuffer(Protocol):
    """
    A Protocol matching [JSSharedArrayBuffer].

    [JSSharedArrayBuffer]: `v8serialize.jstypes.JSSharedArrayBuffer`
    """

    if TYPE_CHECKING:

        @property
        def buffer_id(self) -> SharedArrayBufferId: ...

    else:
        # test/test_protocol_dataclass_interaction.py
        buffer_id = ...


@runtime_checkable
class AnyArrayBufferTransfer(Protocol):
    """
    A Protocol matching [JSArrayBufferTransfer].

    [JSArrayBufferTransfer]: `v8serialize.jstypes.JSArrayBufferTransfer`
    """

    if TYPE_CHECKING:

        @property
        def transfer_id(self) -> TransferId: ...

    else:
        # test/test_protocol_dataclass_interaction.py
        transfer_id = ...


@runtime_checkable
class AnyArrayBufferView(Protocol):
    """
    A Protocol matching [JSJSTypedArray] and [JSJSDataView].

    [JSJSTypedArray]: `v8serialize.jstypes.JSJSTypedArray`
    [JSJSDataView]: `v8serialize.jstypes.JSJSDataView`
    """

    if TYPE_CHECKING:

        @property
        def view_tag(self) -> ArrayBufferViewTag: ...
        @property
        def byte_offset(self) -> int: ...
        @property
        def byte_length(self) -> int: ...
        @property
        def is_length_tracking(self) -> bool: ...
        @property
        def is_backing_buffer_resizable(self) -> bool: ...

    else:
        # test/test_protocol_dataclass_interaction.py
        view_tag = ...
        byte_offset = ...
        byte_length = ...
        is_length_tracking = ...
        is_backing_buffer_resizable = ...


AnyArrayBufferData: TypeAlias = (
    "AnyArrayBuffer | AnySharedArrayBuffer | AnyArrayBufferTransfer"
)
"""Any of the 3 ArrayBuffer types."""

BufferT = TypeVar("BufferT")
BufferT_co = TypeVar("BufferT_co", covariant=True)
BufferT_con = TypeVar("BufferT_con", contravariant=True)
ViewT = TypeVar("ViewT")
ViewT_co = TypeVar("ViewT_co", covariant=True)


class ArrayBufferConstructor(Protocol[BufferT_co]):
    """A function that creates a representation of a serialized ArrayBuffer."""

    @overload
    def __call__(
        self, data: memoryview, *, max_byte_length: None, resizable: Literal[False]
    ) -> BufferT_co: ...

    @overload
    def __call__(
        self, data: memoryview, *, max_byte_length: int, resizable: Literal[True]
    ) -> BufferT_co: ...


class SharedArrayBufferConstructor(Protocol[BufferT_co]):
    """A function that creates a representation of a serialized SharedArrayBuffer."""

    def __call__(self, buffer_id: SharedArrayBufferId) -> BufferT_co: ...


class ArrayBufferTransferConstructor(Protocol[BufferT_co]):
    """A function that creates a representation of a serialized ArrayBufferTransfer."""

    def __call__(self, transfer_id: TransferId) -> BufferT_co: ...


class ArrayBufferViewConstructor(Protocol[BufferT_con, ViewT_co]):
    """A function that creates a representation of a serialized ArrayBuffer view."""

    def __call__(
        self,
        buffer: BufferT_con,
        format: ArrayBufferViewTag,
        *,
        byte_offset: int,
        byte_length: int | None,
    ) -> ViewT_co: ...


class AnyJSError(Protocol):
    """
    A Protocol matching [JSError] and [JSErrorData].

    [JSError]: `v8serialize.jstypes.JSError`
    [JSErrorData]: `v8serialize.jstypes.JSErrorData`
    """

    # properties from protocols mess up concrete classes if they exist at runtime
    if TYPE_CHECKING:

        @property
        def name(self) -> str | JSErrorName: ...
        @name.setter
        def name(self, name: JSErrorName) -> None: ...

        message: str | None
        stack: str | None
        cause: object | None


class JSErrorBuilder(Protocol[T_co]):
    """A function that creates a representation of a serialized Error."""

    def __call__(self, partial: AnyJSError, /) -> tuple[T_co, AnyJSError]: ...
