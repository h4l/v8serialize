from __future__ import annotations

from collections.abc import ByteString
from typing import TYPE_CHECKING
from typing_extensions import (
    Literal,
    NewType,
    Protocol,
    TypeAlias,
    TypeVar,
    overload,
    runtime_checkable,
)

from v8serialize.constants import ArrayBufferViewTag, JSErrorName

if TYPE_CHECKING:
    from typing_extensions import Buffer

    AnyBuffer: TypeAlias = ByteString | Buffer

T_co = TypeVar("T_co", covariant=True)

SharedArrayBufferId = NewType("SharedArrayBufferId", int)
TransferId = NewType("TransferId", int)


@runtime_checkable
class AnyArrayBuffer(Protocol):
    @property
    def data(self) -> AnyBuffer: ...
    @property
    def max_byte_length(self) -> int: ...
    @property
    def resizable(self) -> bool: ...


@runtime_checkable
class AnySharedArrayBuffer(Protocol):
    @property
    def buffer_id(self) -> SharedArrayBufferId: ...


@runtime_checkable
class AnyArrayBufferTransfer(Protocol):
    @property
    def transfer_id(self) -> TransferId: ...


@runtime_checkable
class AnyArrayBufferView(Protocol):
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


AnyArrayBufferData: TypeAlias = (
    AnyArrayBuffer | AnySharedArrayBuffer | AnyArrayBufferTransfer
)

BufferT = TypeVar("BufferT")
BufferT_co = TypeVar("BufferT_co", covariant=True)
BufferT_con = TypeVar("BufferT_con", contravariant=True)
ViewT = TypeVar("ViewT")
ViewT_co = TypeVar("ViewT_co", covariant=True)


class ArrayBufferConstructor(Protocol[BufferT_co]):
    @overload
    def __call__(
        self, data: memoryview, *, max_byte_length: None, resizable: Literal[False]
    ) -> BufferT_co: ...

    @overload
    def __call__(
        self, data: memoryview, *, max_byte_length: int, resizable: Literal[True]
    ) -> BufferT_co: ...


class SharedArrayBufferConstructor(Protocol[BufferT_co]):
    def __call__(self, buffer_id: SharedArrayBufferId) -> BufferT_co: ...


class ArrayBufferTransferConstructor(Protocol[BufferT_co]):
    def __call__(self, transfer_id: TransferId) -> BufferT_co: ...


class ArrayBufferViewConstructor(Protocol[BufferT_con, ViewT_co]):
    def __call__(
        self,
        buffer: BufferT_con,
        format: ArrayBufferViewTag,
        *,
        byte_offset: int,
        byte_length: int | None,
    ) -> ViewT_co: ...


class AnyJSError(Protocol):
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
    def __call__(self, partial: AnyJSError, /) -> tuple[T_co, AnyJSError]: ...
