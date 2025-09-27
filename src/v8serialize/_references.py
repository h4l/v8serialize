from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final, Generator, Generic, NewType, overload

from v8serialize._errors import V8SerializeError

if TYPE_CHECKING:
    from typing_extensions import TypeVar

    T = TypeVar("T", default=object)
else:
    from typing import TypeVar

    T = TypeVar("T")


class ObjectReferenceV8SerializeError(V8SerializeError, KeyError):
    pass


@dataclass(init=False)
class ObjectNotSerializedV8SerializeError(ObjectReferenceV8SerializeError):
    obj: object

    def __init__(self, message: str, *args: object, obj: object) -> None:
        super(ObjectNotSerializedV8SerializeError, self).__init__(message, *args)
        self.obj = obj


@dataclass(init=False)
class SerializedIdOutOfRangeV8SerializeError(ObjectReferenceV8SerializeError):
    serialized_id: SerializedId

    def __init__(self, message: str, serialized_id: SerializedId) -> None:
        super(SerializedIdOutOfRangeV8SerializeError, self).__init__(message)
        self.serialized_id = serialized_id


@dataclass(init=False)
class IllegalCyclicReferenceV8SerializeError(ObjectReferenceV8SerializeError):
    serialized_id: SerializedId
    obj: object

    def __init__(self, message: str, serialized_id: SerializedId, obj: object) -> None:
        super(IllegalCyclicReferenceV8SerializeError, self).__init__(message)
        self.serialized_id = serialized_id
        self.obj = obj


SerializedId = NewType("SerializedId", int)


@dataclass(init=False, slots=True)
class SerializedObjectLog:
    """References to the objects occurring in V8 serialized data.

    The V8 serialization format allow for backreferences to
    objects that occurred earlier in th serialized data. This allows for
    de-duplication and cyclic references.
    """

    _serialized_id_by_pyid: dict[int, SerializedId]
    _object_by_serialized_id: list[object]

    def __init__(self) -> None:
        self._serialized_id_by_pyid = dict()
        self._object_by_serialized_id = []

    def __contains__(self, obj: object) -> bool:
        return id(obj) in self._serialized_id_by_pyid

    def get_serialized_id(self, obj: object) -> SerializedId:
        try:
            serialized_id = self._serialized_id_by_pyid[id(obj)]
            value = self._object_by_serialized_id[serialized_id]
            if isinstance(value, ForwardReference):
                value.get_value()  # throw if not yet set
            return serialized_id
        except KeyError:
            raise ObjectNotSerializedV8SerializeError(
                "Object has not been recorded in the log", obj=obj
            ) from None

    def get_object(self, serialized_id: SerializedId) -> object:
        try:
            return self._object_by_serialized_id[serialized_id]
        except IndexError:
            raise SerializedIdOutOfRangeV8SerializeError(
                "Serialized ID has not been recorded in the log",
                serialized_id=serialized_id,
            ) from None

    def record_reference(self, obj: object) -> SerializedId:
        serialized_id = SerializedId(len(self._object_by_serialized_id))
        self._object_by_serialized_id.append(obj)
        self._serialized_id_by_pyid[id(obj)] = serialized_id
        return serialized_id

    @contextmanager
    def record_acyclic_reference(
        self, obj: object, *, error_detail: str | None = None
    ) -> Generator[SerializedId]:
        """Create a reference to an object that's initially inaccessible.

        This is a context manager, the object cannot be dereferenced or resolved
        until the context manager block ends.
        """
        forward_reference = ForwardReference()
        serialized_id = self.record_reference(obj)
        self.replace_reference(serialized_id, forward_reference)

        try:
            yield serialized_id
        except ForwardReferenceError as e:
            if e.forward_reference is forward_reference:
                msg = "An illegal cyclic reference was made to an object"
                if error_detail:
                    msg = f"{msg}: {error_detail}"
                raise IllegalCyclicReferenceV8SerializeError(
                    msg, serialized_id=serialized_id, obj=obj
                ) from e
            raise
        finally:
            forward_reference.set_value(obj)

    def replace_reference(self, serialized_id: SerializedId, value: object) -> None:
        if serialized_id != len(self._object_by_serialized_id) - 1:
            raise ValueError(
                f"Only the most-recent reference can be replaced: most "
                f"recent={len(self._object_by_serialized_id) - 1}, "
                f"serialized_id={serialized_id}"
            )
        self._object_by_serialized_id[serialized_id] = value


_sentinel: Final[Any] = object()


class ForwardReferenceError(ReferenceError, Generic[T]):
    forward_reference: ForwardReference[T]

    def __init__(self, message: str, forward_reference: ForwardReference[T]) -> None:
        super().__init__(message)
        self.forward_reference = forward_reference


@dataclass(init=False, slots=True)
class ForwardReference(Generic[T]):
    __value: T

    @overload
    def __init__(self) -> None: ...

    @overload
    def __init__(self, *, value: T) -> None: ...

    def __init__(self, *, value: T = _sentinel) -> None:
        self.__value = value

    def get_value(self) -> T:
        value = self.__value
        if value is _sentinel:
            raise ForwardReferenceError("ForwardReference has no value set", self)
        return value

    def set_value(self, value: T) -> None:
        if self.__value is not _sentinel:
            raise ForwardReferenceError("ForwardReference already has a value", self)
        self.__value = value

    def __repr__(self) -> str:
        if self.__value is _sentinel:
            return "ForwardReference()"
        try:
            return f"ForwardReference(value={self.__value!r})"
        except RecursionError:
            return "ForwardReference(value=...)"
