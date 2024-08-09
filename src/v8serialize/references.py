from __future__ import annotations

from dataclasses import dataclass
from typing import NewType

from v8serialize.errors import V8CodecError


@dataclass()
class ObjectReferenceV8CodecError(V8CodecError, KeyError):
    pass


@dataclass(slots=True, init=False)
class ObjectNotSerializedV8CodecError(ObjectReferenceV8CodecError):
    obj: object

    def __init__(self, message: str, *args: object, obj: object) -> None:
        super(ObjectNotSerializedV8CodecError, self).__init__(message, *args)
        self.obj = obj


@dataclass(slots=True, init=False)
class SerializedIdOutOfRangeV8CodecError(ObjectReferenceV8CodecError):
    serialized_id: SerializedId

    def __init__(self, message: str, serialized_id: SerializedId) -> None:
        super(SerializedIdOutOfRangeV8CodecError, self).__init__(message)
        self.serialized_id = serialized_id


SerializedId = NewType("SerializedId", int)


@dataclass(slots=True, init=False)
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
            return self._serialized_id_by_pyid[id(obj)]
        except KeyError:
            raise ObjectNotSerializedV8CodecError(
                "Object has not been recorded in the log", obj=obj
            )

    def get_object(self, serialized_id: SerializedId) -> object:
        try:
            return self._object_by_serialized_id[serialized_id]
        except IndexError:
            raise SerializedIdOutOfRangeV8CodecError(
                "Serialized ID has not been recorded in the log",
                serialized_id=serialized_id,
            )

    def record_reference(self, obj: object) -> SerializedId:
        serialized_id = SerializedId(len(self._object_by_serialized_id))
        self._object_by_serialized_id.append(obj)
        self._serialized_id_by_pyid[id(obj)] = serialized_id
        return serialized_id
