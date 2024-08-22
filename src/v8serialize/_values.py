from __future__ import annotations

from typing import (
    TYPE_CHECKING,
    ByteString,
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
    def byte_length(self) -> int | None: ...


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
    @property
    def name(self) -> str: ...
    @property
    def message(self) -> str | None: ...
    @property
    def stack(self) -> str | None: ...
    @property
    def cause(self) -> object | None: ...


class AnyJSErrorSettableCause(AnyJSError, Protocol):
    """AnyJSError with a settable cause property."""

    cause: object | None


class JSErrorConstructor(Protocol[T_co]):
    def __call__(
        self, *, name: JSErrorName, message: str | None, stack: str | None
    ) -> T_co: ...


if TYPE_CHECKING:
    JSErrorSettableCauseT_co = TypeVar(
        "JSErrorSettableCauseT_co",
        bound=AnyJSErrorSettableCause,
        covariant=True,
        default=AnyJSErrorSettableCause,
    )
else:
    JSErrorSettableCauseT_co = TypeVar(
        "JSErrorSettableCauseT_co", bound=AnyJSErrorSettableCause, covariant=True
    )


class JSErrorSettableCauseConstructor(
    JSErrorConstructor[JSErrorSettableCauseT_co], Protocol[JSErrorSettableCauseT_co]
): ...
